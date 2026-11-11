# About
A modified [HoshimiToolkit](https://github.com/MalitsPlus/HoshimiToolkit) for gkmas.</br>
Please manually change **EncryptedCache/octocacheevai** for any manifest update.</br>
(Current version in repository was **v228**, which is likely useless. Replace it yourself.)

# Requirements
- Python 3.10 or newer (tested on 3.13)
- Core dependencies:

```bash
pip install -r requirements.txt
```

This installs `pycryptodome`, `rich`, `protobuf` and `requests`.

`ImageConvertor.py` additionally needs Pillow:

```bash
pip install -r requirements-optional.txt
```

# Settings in main.py
| Variable | Meaning |
| --- | --- |
| `cache_file` | Path to the encrypted manifest. Replace it manually on every game update. |
| `decrypted_dir` | Where the decrypted manifest (`.json`, `.db`) is written. |
| `output_dir` | Where downloads and unobfuscated assets are written. |
| `download_asset` | `1` to download Unity asset bundles. |
| `download_resource` | `1` to download audio/text resources. |
| `download_worker_num` | Number of download threads. |

# Output layout
```
<output_dir>/Assets/<md5>                                        downloaded asset bundles, named by md5
<output_dir>/UnobfuscateAssets/<revision>/<type>/<name>.unity3d  deobfuscated bundles
<output_dir>/Resource/<type>/<name>                              audio / text / video resources
<decrypted_dir>/manifest_v<revision>                             decrypted manifest, JSON and SQLite
```

# Extracting the bundles
The `*.unity3d` files produced above are still Unity bundles. Use a Unity asset
extractor such as [AssetStudio](https://github.com/Perfare/AssetStudio) or
[AssetRipper](https://github.com/AssetRipper/AssetRipper) to get the actual
textures, models and audio out of them.

`ImageConvertor.py` is a separate, standalone helper and does **not** read
`.unity3d` files. It takes PNGs exported by such an extractor, resizes each one
to 1820x1024 (the source textures are 2048x1024 with extra padding) and saves it
as lossless WebP. Adjust the `input` and `output` paths at the top of that file
before running it.

# Disclaimer
Use at your own risk.</br>
You shall take responsibilities for any possible consequence of using this tool and related assets.
