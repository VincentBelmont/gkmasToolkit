from rich.console import Console
from pathlib import Path

console = Console()

def unObfuscate(jDict: dict, offset: int = 0, streamPos: int = 0, headerLength: int = 256, baseDir: str = "./gkmas"):
    """
    Args: 
        assetList (list): Assets list to unobfuscate
        baseDir (str): Directory that holds 'Assets' and receives 'UnobfuscateAssets'
    """
    inputDirectory = Path(baseDir).joinpath("Assets")
    outputPath = Path(baseDir).joinpath("UnobfuscateAssets")
    assetList: list = jDict["assetBundleList"]
    md5NameDict = {
        it["md5"] : it["name"]
        for it in assetList
    }
    md5TypeDict = {
        it["md5"] : it["type"]
        for it in assetList
    }
    if not inputDirectory.is_dir():
        console.print(f"[bold red]>>> [Error][/bold red] Folder '{inputDirectory}' does not exist. Unobfuscation has been discarded.")
        return
    filePaths = [path for path in inputDirectory.glob("**/*") if path.name in md5NameDict]

    filePaths.sort(key=lambda x: x.name)
    unitySignature = b"\x55\x6e\x69\x74\x79"    # Unity
    count = 0
    allCount = filePaths.__len__()
    errorCount = 0
    for path in filePaths:
        count += 1
        md5 = path.name
        name = md5NameDict.get(md5)
        _type = md5TypeDict.get(md5)
        exportFolder = outputPath.joinpath(str(jDict["revision"])).joinpath(_type)
        exportFile = exportFolder.joinpath(name + ".unity3d")
        # Skip when the exported copy is already complete. Unobfuscating rewrites
        # bytes in place, so a finished export always has the same length as its
        # source; anything shorter is a leftover from an interrupted run.
        if exportFile.is_file() and exportFile.stat().st_size == path.stat().st_size:
            console.print(f"[bold white]>>> [Skipped][/bold white] ({count}/{allCount}) Assetbundle '{ name }.unity3d' has already been unobfuscated.")
            continue
        buff = path.read_bytes()
        if buff[0:5] == unitySignature:
            exportFolder.mkdir(parents=True, exist_ok=True)
            exportFile.write_bytes(buff)
            console.print(f"[bold withe]>>> [Info][/bold withe] ({count}/{allCount}) Assetbundle '{ name }.unity3d' is a non-obfuscated file.")
            continue
        else:
            unityFS = __cryptByString(buff, md5NameDict[md5], offset, streamPos, headerLength)
            if unityFS.__len__() > 0 and unityFS[0:5] == unitySignature:
                exportFolder.mkdir(parents=True, exist_ok=True)
                flag = exportFile.write_bytes(unityFS)
                if flag:
                    console.print(f"[bold green]>>> [Succeed][/bold green] ({count}/{allCount}) Assetbundle '{ name }.unity3d' has been successfully unobfuscated.")
                else:
                    errorCount += 1
                    console.print(f"[bold red]>>> [Error][/bold red] ({count}/{allCount}) Writes assetbundle '{ name }.unity3d' failed.")
            else:
                errorCount += 1
                console.print(f"[bold red]>>> [Error][/bold red] ({count}/{allCount}) Unobfuscates assetbundle '{ name }.unity3d' failed.")
                
    console.print(f"[bold white]>>> [Info][/bold white] Unobfuscating operations all done, { errorCount } error(s) were occurred during the entire workflow.")

def __stringToMaskBytes(maskString: str, maskStringLength: int, bytesLength: int) -> bytes:
    # maskBytes = bytes(bytesLength)
    maskBytes = bytearray(bytesLength)
    if maskString != 0:
        if maskStringLength >= 1:
            i = 0
            j = 0
            k = bytesLength - 1
            while maskStringLength != j:
                charJ = maskString[j]
                charJ = int.from_bytes(charJ.encode("ascii"), byteorder='little', signed=False)  # Must be casted as Int in python 
                j += 1
                maskBytes[i] = charJ
                i += 2
                charJ = ~charJ & 0xFF   # You must add &0xFF to get a unsigned integer in python or it will return the signed one
                maskBytes[k] = charJ    #.to_bytes(length=1, byteorder="little", signed=True)
                k -= 2
        if bytesLength >= 1:
            l = bytesLength
            v13 = 0x9B
            m = bytesLength
            pointer = 0
            while m:
                v16 = maskBytes[pointer]
                pointer += 1
                m -= 1
                v13 = (((v13 & 1) << 7) | (v13 >> 1)) ^ v16
            b = 0
            while l:
                l -= 1
                maskBytes[b] ^= v13
                b += 1
    return bytes(maskBytes)

def __cryptByString(input: bytes, maskString: str, offset: int, streamPos: int, headerLength: int) -> bytes:
    inputLength = input.__len__()
    maskStringLength = maskString.__len__()
    bytesLength = maskStringLength << 1
    buffer = bytearray(input)
    maskBytes = __stringToMaskBytes(maskString, maskStringLength, bytesLength)
    i = 0
    while streamPos + i < headerLength:
        buffer[offset + i] ^= maskBytes[streamPos + i - int((streamPos + i) / bytesLength) * bytesLength]
        i += 1
    return bytes(buffer)
