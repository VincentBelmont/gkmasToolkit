import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# (connect, read) timeout in seconds. Sized for multi-hundred-MB files on a slow
# link: 60s is per socket read, not per file. Without it a black-holed connection
# blocks a worker forever and the whole run never finishes.
REQUEST_TIMEOUT = (10, 60)

# Retry policy for transient network failures. MAX_RETRIES counts only the
# retries after the first attempt, so the worst case is MAX_RETRIES + 1 tries.
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0   # seconds; doubles after each retry (1s, 2s, 4s, ...)

# URL template used when the manifest does not carry one; {o} is the object name.
DEFAULT_URL_FORMAT = "https://object.asset.game-gakuen-idolmaster.jp/{o}"

# Files that exhausted their retries during this run, collected for the final summary.
_FAILED_DOWNLOADS = []

def _buildUrl(urlFormat, objectName):
    """Expands the URL template taken from the manifest.

    Supports the '{o}' placeholder used today and a plain prefix ending in '/',
    and falls back to the built-in CDN when the format is unrecognised.
    """
    if not isinstance(urlFormat, str) or not urlFormat:
        urlFormat = DEFAULT_URL_FORMAT
    if "{o}" in urlFormat:
        return urlFormat.replace("{o}", objectName)
    if urlFormat.endswith("/"):
        return urlFormat + objectName
    print(f">>> [Warn] Unsupported urlFormat {urlFormat!r}, falling back to the built-in CDN.")
    return DEFAULT_URL_FORMAT.replace("{o}", objectName)

def _stream_to_file(file_path: str, response, expectedSize=None):
    """Streams the response body into a sibling .part file and swaps it in.

    Returns the byte count when the payload is complete and matches expectedSize
    (when the manifest states one); returns None after discarding a short read.
    A failed transfer or write never leaves a partial file at the final path.
    """
    tempPath = f"{file_path}.part"
    written = 0
    try:
        with open(tempPath, 'wb') as f:
            for chunk in response.iter_content(1024 * 1024):
                f.write(chunk)
                written += len(chunk)
        if expectedSize is not None and written != expectedSize:
            os.remove(tempPath)
            return None
        os.replace(tempPath, file_path)
        return written
    except BaseException:
        try:
            os.remove(tempPath)
        except OSError:
            pass
        raise

def download_file(url, file_path, name, count, total, is_asset, expectedSize=None):
    type_desc = "Assetbundle" if is_asset else "ResourceBundle"
    attempts = MAX_RETRIES + 1
    reason = "unknown"
    for attempt in range(1, attempts + 1):
        try:
            # stream=True keeps peak memory at one chunk per worker instead of the
            # whole payload, which for the 1 GB resources would be several GB.
            with requests.get(url, timeout=REQUEST_TIMEOUT, stream=True) as response:
                if response.status_code == 200:
                    if _stream_to_file(file_path, response, expectedSize) is not None:
                        print(f">>> [Succeed] ({count}/{total}) {type_desc} '{name}' has been saved as {file_path}.")
                        return True
                    # A short payload is usually a dropped connection, so let the
                    # normal retry ladder handle it instead of failing outright.
                    reason = f"size mismatch (expected {expectedSize}B)"
                else:
                    reason = f"HTTP {response.status_code}"
                    # 4xx (429 Too Many Requests aside) will not improve on retry: fail fast,
                    # but still record it as a failure so the final summary is complete.
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        print(f">>> [Failed] ({count}/{total}) {type_desc} '{name}' not retried ({reason}, client error).")
                        _FAILED_DOWNLOADS.append((name, reason))
                        return False
        except requests.RequestException as e:
            reason = type(e).__name__
        if attempt < attempts:
            delay = RETRY_BACKOFF * (2 ** (attempt - 1))
            print(f">>> [Retry] ({count}/{total}) {type_desc} '{name}' attempt {attempt}/{attempts} failed ({reason}), retrying in {delay:.0f}s.")
            time.sleep(delay)
    print(f">>> [Failed] ({count}/{total}) {type_desc} '{name}' giving up after {attempts} attempt(s), last error: {reason}.")
    _FAILED_DOWNLOADS.append((name, reason))
    return False

def _collect_failures(futures: dict, kind: str):
    """Drains finished downloads and accounts for anything that still raises.

    Network failures are already handled inside download_file(), so an exception
    reaching this point is a local problem (disk full, permissions, AV lock).
    It is logged and counted instead of aborting the whole run.
    """
    aborted = 0
    for future in as_completed(futures):
        try:
            future.result()
        except Exception as e:
            aborted += 1
            name = futures[future]
            print(f">>> [Error] {kind} '{name}' aborted: {type(e).__name__}: {e}")
            _FAILED_DOWNLOADS.append((name, f"{type(e).__name__}: {e}"))
    if aborted:
        print(f">>> [Summary] {aborted} {kind}(s) aborted by local errors.")

def download(jdic: dict, download_dir: str, download_asset: int, download_resource: int, num_worker: int, urlFormat: str = None):
    assetBundleList: list = jdic['assetBundleList']
    resourceList: list = jdic['resourceList']
    assetnum = len(assetBundleList)
    resourcenum = len(resourceList)
    assetpath = f"{download_dir}/Assets"
    resourcepath = f"{download_dir}/Resource"
    # The manifest owns the CDN template; the built-in constant is only a fallback.
    urlFormat = urlFormat or jdic.get("urlFormat") or DEFAULT_URL_FORMAT
    
    print("Total asset number is:", assetnum)
    print("Total resource number is:", resourcenum)
    
    os.makedirs(download_dir, exist_ok=True)
    
    executor = ThreadPoolExecutor(max_workers=num_worker)

    if download_asset:
        print("Start downloading asset files...")
        if not os.path.exists(assetpath):
            os.mkdir(assetpath)
        futures = {}
        for count, asset in enumerate(assetBundleList, start=1):
            ab_name = asset['name']
            object_name = asset['objectName']
            md5_name = asset['md5']
            url = _buildUrl(urlFormat, object_name)
            file_path = os.path.join(assetpath, md5_name)
            # An existing file is only reused when its size still matches the manifest:
            # a truncated payload (aborted write) would otherwise be trusted forever.
            expectedSize = asset.get('size')
            presentSize = os.path.getsize(file_path) if os.path.isfile(file_path) else None
            if presentSize is not None and (expectedSize is None or presentSize == expectedSize):
                print(f">>> [Skipped] ({count}/{assetnum}) Assetbundle '{ab_name}.unity3d' saved as {md5_name} has existed.")
                continue
            if presentSize is not None:
                print(f">>> [Stale] ({count}/{assetnum}) Assetbundle '{ab_name}.unity3d' is {presentSize}B but manifest says {expectedSize}B, fetching again.")
            futures[executor.submit(download_file, url, file_path, ab_name, count, assetnum, True, expectedSize)] = ab_name
        
        _collect_failures(futures, "asset bundle")

    if download_resource:
        print("Start downloading resource files...")
        if not os.path.exists(resourcepath):
            os.mkdir(resourcepath)
        # Resources need no post-processing, so they are stored under their final
        # name right away, grouped by the type prefix (sud/adv/mov/img/...).
        for resourceType in sorted({res.get('type', 'others') for res in resourceList}):
            os.makedirs(os.path.join(resourcepath, resourceType), exist_ok=True)
        futures = {}
        for count, res in enumerate(resourceList, start=1):
            res_name = res['name']
            object_name = res['objectName']
            md5_name = res['md5']
            url = _buildUrl(urlFormat, object_name)
            file_path = os.path.join(resourcepath, res.get('type', 'others'), res_name)
            expectedSize = res.get('size')
            presentSize = os.path.getsize(file_path) if os.path.isfile(file_path) else None
            if presentSize is not None and (expectedSize is None or presentSize == expectedSize):
                print(f">>> [Skipped] ({count}/{resourcenum}) ResourceBundle '{res_name}' has existed.")
                continue
            if presentSize is not None:
                print(f">>> [Stale] ({count}/{resourcenum}) ResourceBundle '{res_name}' is {presentSize}B but manifest says {expectedSize}B, fetching again.")
            futures[executor.submit(download_file, url, file_path, res_name, count, resourcenum, False, expectedSize)] = res_name
        
        _collect_failures(futures, "resource bundle")

    executor.shutdown()
    if _FAILED_DOWNLOADS:
        print(f">>> [Summary] {len(_FAILED_DOWNLOADS)} file(s) could not be downloaded. Re-run to retry them (complete files are skipped, stale ones are fetched again).")
        for failedName, failedReason in _FAILED_DOWNLOADS[:20]:
            print(f"    - {failedName} ({failedReason})")
        if len(_FAILED_DOWNLOADS) > 20:
            print(f"    ... and {len(_FAILED_DOWNLOADS) - 20} more.")
    else:
        print(">>> [Summary] No download failures.")
    print("All files downloaded.")
