import hashlib
import json
import octodb_pb2
import sqlite3
import sys
import re
from rich.console import Console
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pathlib import Path
from google.protobuf.json_format import MessageToJson

# Currently known magic strings
__KEY = "1nuv9td1bw1udefk"
__IV = "LvAUtf+tnz"

# Input cache file and output directory strings
__inputPathString = "./EncryptedCache/octocacheevai"
__outputPathString = "./DecryptedCache"

# Column order shared by the assetBundleList and resourceList tables, used when
# binding rows as SQL parameters.
__COLUMNS = ("id", "filepath", "name", "size", "crc", "priority", "tagid",
             "dependencie", "state", "md5", "objectName", "generation",
             "uploadVersionId", "type")

def __scalarValue(value):
    """SQLite can only bind scalars. Repeated protobuf fields reach us as lists,
    so flatten those to the same textual form the table has always stored."""
    if isinstance(value, (list, tuple)):
        return str(list(value))
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value

# Initialization
console = Console()

def __decryptCache(key = __KEY, iv = __IV, inputPath = __inputPathString, outputDir = __outputPathString) -> octodb_pb2.Database:
    """Decrypts a cache file (usually named 'octocacheevai') and deserializes it to a protobuf object

    Args:
        key (string): A byte-string. Currently 16 characters long and appears to be alpha-numeric.
        iv (string): A byte-string. Currently 10 characters long and appears to be base64-ish.

    Returns:
        octodb_pb2.Database: A protobuf object representing the deserialized cache.
    """
    key = bytes(key, "utf-8")
    iv = bytes(iv, "utf-8")

    key = hashlib.md5(key).digest()
    iv = hashlib.md5(iv).digest()

    cipher = AES.new(key, AES.MODE_CBC, iv)
    encryptCachePath = Path(inputPath)

    try:
        encryptedBytes = encryptCachePath.read_bytes()
    except:
        console.print(f"[bold red]>>> [Error][/bold red] Failed to load encrypted cache file at '{encryptCachePath}'.\n{sys.exc_info()}\n")
        raise

    try:
        # For some reason there's a single extra 0x01 byte at the start of the encrypted file
        decryptedBytes = unpad(cipher.decrypt(encryptedBytes[1:]), block_size = 16, style = "pkcs7")
    except:
        console.print(f"[bold red]>>> [Error][/bold red] Failed to decrypt cache file.\n{sys.exc_info()}\n")
        raise

    # The first 16 bytes are an md5 hash of the database that follows it, which is skipped because it's useless for this purpose
    decryptedBytes = decryptedBytes[16:]
    # Read the decrypted bytes to a protobuf object
    protoDatabase = octodb_pb2.Database()
    protoDatabase.ParseFromString(decryptedBytes)
    # Revision number should probably change with every update..?
    console.print(f"[bold]>>> [Info][/bold] Current revision : {protoDatabase.revision}\n")
    # Get output dir and append it to the filename
    outputPath = Path(f"{outputDir}/manifest_v{protoDatabase.revision}")
    # Write the decrypted cache to a local file
    try:
        outputPath.parent.mkdir(parents=True, exist_ok=True)
        outputPath.write_bytes(decryptedBytes)
        console.print(f"[bold green]>>> [Succeed][/bold green] Decrypted cache has been written into {outputPath}.\n")
    except:
        console.print(f"[bold red]>>> [Error][/bold red] Failed to write decrypted file into {outputPath}.\n{sys.exc_info()}\n")
        raise

    return protoDatabase

def __protoDb2Json(protoDb: octodb_pb2.Database) -> str:
    """Converts a protobuf serialized object to JSON string then return the string."""
    jsonDb = MessageToJson(protoDb)
    return jsonDb

def __createSQLiteDB(jDict: dict, outputString: str):
    """Converts json to SQLite database."""
    try:
        conn = sqlite3.connect(outputString)
    except:
        console.print(f"[bold red]>>> [Error][/bold red] Failed to connect or create db file.\n{sys.exc_info()}\n")
        return

    cur = conn.cursor()
    try:
        num = cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('manifest', 'assetBundleList', 'resourceList')").fetchone()
        if num[0] < 1:
            cur.execute("""
            CREATE TABLE manifest (
            revision INTEGER,
            urlFormat TEXT,
            tagname TEXT )
            """)
            cur.execute("""
            CREATE TABLE assetBundleList (
            id INTEGER PRIMARY KEY,
            filepath TEXT,
            name TEXT,
            size INTEGER,
            crc INTEGER,
            priority INTEGER,
            tagid TEXT,
            dependencie TEXT,
            state TEXT,
            md5 TEXT,
            objectName TEXT,
            generation INTEGER,
            uploadVersionId INTEGER,
            type TEXT )
            """)
            cur.execute("""
            CREATE TABLE resourceList (
            id INTEGER PRIMARY KEY,
            filepath TEXT,
            name TEXT,
            size INTEGER,
            crc INTEGER,
            priority INTEGER,
            tagid TEXT,
            dependencie TEXT,
            state TEXT,
            md5 TEXT,
            objectName TEXT,
            generation INTEGER,
            uploadVersionId INTEGER,
            type TEXT )
            """)
            conn.commit()
            console.print(f"[bold green]>>> [Succeed][/bold green] Tables have been created successfully.\n")
        else:
            console.print(f"[bold yellow]>>> [Warning][/bold yellow] Tables are already exists.\n")
    except:
        conn.rollback()
        conn.close()
        console.print(f"[bold red]>>> [Error][/bold red] Failed to create tables.\n{sys.exc_info()}\n")
        return

    try:
        revision = jDict.get("revision")
        urlFormat = jDict.get("urlFormat")
        tagname = __scalarValue(jDict.get("tagname"))

        cur.execute("DELETE FROM manifest")
        cur.execute(
            "INSERT INTO manifest (revision, urlFormat, tagname) VALUES (?, ?, ?)",
            (revision, urlFormat, tagname),
        )

        # Every value is bound as a parameter: manifest fields are third-party data
        # and must never be spliced into SQL text.
        placeholders = ", ".join("?" * len(__COLUMNS))
        for table in ("assetBundleList", "resourceList"):
            cur.executemany(
                "INSERT OR REPLACE INTO " + table
                + " (" + ", ".join(__COLUMNS) + ") VALUES (" + placeholders + ")",
                [tuple(__scalarValue(row.get(column)) for column in __COLUMNS) for row in jDict[table]],
            )

        conn.commit()
        console.print("[bold green]>>> [Succeed][/bold green] All data has been written into SQLite database.\n")
    except :
        conn.rollback()
        conn.close()
        console.print(f"[bold red]>>> [Error][/bold red] Failed to insert data into tables.\n{sys.exc_info()}\n")
        raise
        return

    conn.close()
    return

def __writeJsonFile(d: dict, path: Path):
    # Write the string to a json file
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, sort_keys=True, indent=4))
        console.print(f"[bold green]>>> [Succeed][/bold green] JSON has been written into {path}.\n")
    except:
        console.print(f"[bold red]>>> [Error][/bold red] Failed to write JSON into {path}.\n{sys.exc_info()}\n")
        raise

def __appendType(d: dict) -> dict:
    for it in d["assetBundleList"]:
        m = re.match(r"(.+?)_.*$", it["name"])  # Matches first _ in name
        if m:
            typeStr = m.group(1)
        else:
            typeStr = "others"
        it["type"] = typeStr
    for it in d["resourceList"]:
        m = re.match(r"(.+?)_.*$", it["name"])  # Matches first _ in name
        if m:
            typeStr = m.group(1)
        else:
            typeStr = "others"
        it["type"] = typeStr
    return d

def doDecrypt(inputPath = __inputPathString, outputDir = __outputPathString) -> dict:
    # Decrypt cache file
    protoDb = __decryptCache(inputPath = inputPath, outputDir = outputDir)
    # Convert protobuf to json string
    jsonString = __protoDb2Json(protoDb)
    # Deserialize json string to a dict
    jDict = json.loads(jsonString)
    jDict = __appendType(jDict)
    # Define SQLite DB file output path string
    pathString = Path(f"{outputDir}/manifest_v{jDict['revision']}.db")
    # Create SQLite DB file
    __createSQLiteDB(jDict, pathString)
    # Define the output path of json file
    outputPath = Path(f"{outputDir}/manifest_v{protoDb.revision}.json")
    # Write the json string into a file
    __writeJsonFile(jDict, outputPath)
    return jDict
