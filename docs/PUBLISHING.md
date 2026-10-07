# Put this repository on GitHub

The folder is already a local Git repository with a `main` branch. Create an empty GitHub repository without an initial README/license, then run these commands from the local repository directory:

```powershell
git remote add origin https://github.com/YOUR-NAME/ashes-cpp-lab.git
git push -u origin main
```

Suggested description:

> Experimental AI-generated C++ Ashes of Creation exploration server: terrain movement, flight and a live Web UI. Bring your own client. Very buggy; no combat.

Suggested topics: `ashes-of-creation`, `cpp`, `private-server`, `game-preservation`, `terrain`, `experimental`.

The provided ZIP contains tracked source, docs and media, with no game files or local test artifacts. If you start from the ZIP rather than the Git folder, initialize Git and commit its files first. Do not upload the original research workspace or generated `CPP/data/` and client-profile directories.

The README's GIFs use relative paths. It embeds short previews and links to complete GIF recordings. No MP4s or original recording files are included.
