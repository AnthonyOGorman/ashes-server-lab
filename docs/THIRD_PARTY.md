# Third-party notices

| Component | Use | License / source |
| --- | --- | --- |
| nlohmann/json 3.11.3 | Vendored C++ JSON headers | [MIT notice](nlohmann-LICENSE.txt), [upstream](https://github.com/nlohmann/json) |
| nghttp2 headers/runtime | HTTP/2 lobby framing; runtime installed by user | [MIT notice](nghttp2-LICENSE.txt), [upstream](https://github.com/nghttp2/nghttp2) |
| OpenSSL headers/libcrypto | SHA-256 and cryptographic primitives; runtime installed by user | [Apache 2.0 license](openssl-LICENSE.txt), [upstream](https://github.com/openssl/openssl) |
| SQLite header/runtime | Local packet/event store; runtime installed by user | [Public-domain notice](sqlite3-LICENSE.txt), [upstream](https://www.sqlite.org/) |
| CUE4Parse 1.2.2.202610 | Offline archive parsing; restored from NuGet | [Upstream license](https://github.com/FabianFG/CUE4Parse/blob/master/LICENSE) |
| Microsoft.Bcl.Memory 10.0.9 | Extractor dependency; restored from NuGet | [dotnet/runtime license](https://github.com/dotnet/runtime/blob/main/LICENSE.TXT) |
| NumPy | Offline math/buffer validation; installed by user | [Upstream license](https://numpy.org/doc/stable/license.html) |

MSYS2's dependency DLLs and their transitive runtimes are installed by the user and copied into ignored local build directories. No binary release of those libraries is included here. If you distribute a compiled release, review the licenses and notices for every DLL you include, including GNU runtimes.

Oodle, the original EOS SDK, Unreal Engine/client binaries and game archives are not distributed. The local EOS shim is original compatibility code built from this repository; it is not Epic's SDK. Game-rendered media is illustrative and remains subject to its owners' rights. The MIT license applies to original lab code, not the game or third-party components.
