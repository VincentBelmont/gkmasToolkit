# IDOLY PRIDE leftover, kept for reference only.
#
# This decrypts a single "storage" file with AES-256-CBC. The KEY and IV below were
# recovered from the IDOLY PRIDE client and are NOT verified against gkmas: no
# gkmas storage file was available to test with. Treat this as a reference recipe
# for the format, not as a working tool for this project.
#
# Note on the material: the original code called decryptStorageFile(IV, KEY[9:25]),
# i.e. the AES key came from the IV string and the IV from a slice of KEY. That is
# preserved below as AES_KEY / AES_IV so the same bytes are used.
#
# Usage:
#   python legacy/StorageDecryptor.py <encrypted-file> [output-file]

import sys
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

KEY = "b9d8b4d1bfb2240b2a96efbdca519474"
IV = "1b07142724cd64ea7a583374ba889667"

AES_KEY = IV          # 32 bytes -> AES-256
AES_IV = KEY[9:25]    # 16 bytes -> CBC block size


def decryptStorageFile(inputPath, outputPath=None, key=AES_KEY, iv=AES_IV):
    """Decrypts one storage file and writes the result next to it by default."""
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    decryptedBytes = cipher.decrypt(Path(inputPath).read_bytes())
    # The client appears to use PKCS#7 without hashing the key/iv first; if a given
    # file fails here, try md5(key).digest() / md5(iv).digest() instead.
    decryptedBytes = unpad(decryptedBytes, block_size=16, style="pkcs7")

    outPath = Path(outputPath) if outputPath else Path(str(inputPath) + "_decrypt")
    outPath.write_bytes(decryptedBytes)
    return outPath


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("usage: python legacy/StorageDecryptor.py <encrypted-file> [output-file]")
        raise SystemExit(2)

    written = decryptStorageFile(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"decrypted -> {written}")
