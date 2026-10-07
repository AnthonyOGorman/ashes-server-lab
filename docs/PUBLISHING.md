# Publishing Ashes Server Lab

The public repository is [AnthonyOGorman/ashes-server-lab](https://github.com/AnthonyOGorman/ashes-server-lab), with its [documentation site](https://anthonyogorman.github.io/ashes-server-lab/) published from **main → /docs**.

## Maintain the static site

`docs/.nojekyll` disables Jekyll: the committed HTML contains complete visible text and requires no JavaScript. The README and existing technical Markdown remain the source of truth. `tools/site/home.md` provides the landing page and `docs/FAQ.md` provides the FAQ. The builder renders those sources and the important existing docs, rewriting links and adding metadata, canonical URLs and crawl files.

After editing source documentation, regenerate from the repository root:

```powershell
python -m pip install -r tools/site/requirements.txt
python tools/site/build.py
python tools/site/build.py --check
git diff --check
```

Commit source and generated files together. The documentation workflow detects stale output and validates internal links/anchors, canonical URLs and sitemap consistency. A push to `main` triggers GitHub's branch-based Pages deployment. Do not hand-edit generated HTML. This validation does not test native server behavior.

`tools/site/site.css` and `tools/site/llms.txt` are the stylesheet and curated guide sources. `docs/social-preview.png` is a text-only branding image without game artwork. Website Open Graph/Twitter metadata references it; GitHub's separate repository preview can be uploaded at **Settings → General → Social preview**.

## Crawling and Search Console

The sitemap lists only the nine actual public HTML pages. `llms.txt` helps readers navigate the project; it does not guarantee AI inclusion or indexing. A permissive `robots.txt` is served beside the sitemap, but crawlers read robots rules at the **origin root**, `https://anthonyogorman.github.io/robots.txt`. This project repository cannot control that root file. If a user-site repository later supplies root robots rules, keep `/ashes-server-lab/` crawlable and reference this sitemap there.

Add the URL-prefix property `https://anthonyogorman.github.io/ashes-server-lab/` in Google Search Console. Google's HTML verification file can be committed under `docs/` with its exact supplied filename/content; alternatively, add its verification meta tag to the homepage template in `tools/site/build.py`. Never commit credentials or account/session data. After deployment, verify ownership, submit `sitemap.xml`, and request indexing of the homepage and `faq.html` through URL Inspection. Indexing is not immediate or guaranteed.

## Publishing a fresh source copy

The folder is already a local Git repository with a `main` branch. Create an empty GitHub repository without an initial README/license, then run these commands from the local repository directory:

```powershell
git remote add origin https://github.com/YOUR-NAME/ashes-server-lab.git
git push -u origin main
```

Suggested description:

> Experimental open-source C++20 Ashes of Creation private-server / server-emulation lab for local Verra exploration, terrain collision, movement, flight and live browser tools. Very buggy; bring your own client. No combat or quests.

The existing repository topics are managed separately; site maintenance does not modify them.

The provided ZIP contains tracked source, docs and media, with no game files or local test artifacts. If you start from the ZIP rather than the Git folder, initialize Git and commit its files first. Do not upload the original research workspace or generated `CPP/data/` and client-profile directories.

The README's GIFs use relative paths. It embeds short previews and links to complete GIF recordings. No MP4s or original recording files are included.
