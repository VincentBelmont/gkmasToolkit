from ManifestDecryptor import doDecrypt
from MaskedHeaderStream import unObfuscate
from Downloader import download

cache_file = "./EncryptedCache/octocacheevai"
decrypted_dir = "./DecryptedCache"
output_dir = "./gkmas"

download_asset = 1
download_resource = 0
download_worker_num = 16

jDict = doDecrypt(cache_file, decrypted_dir)

download(jDict, output_dir, download_asset, download_resource, download_worker_num)

unObfuscate(jDict, baseDir=output_dir)
