# LinkedIn "Grab Jobs" Bookmarklet

Runs **in your own browser, in your logged-in session** — no scraping of
LinkedIn's servers, no automation of your account. You click it on a LinkedIn
jobs page and it copies every visible job link to your clipboard, ready to paste
into `INBOX.md`.

## Install
1. Create a new bookmark in your browser (bookmark any page, then edit it).
2. Name it **"Grab Jobs → clipboard"**.
3. Replace the URL/address with the code below (all one line):

```
javascript:(()=>{const ids=new Set();document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a=>{const m=a.href.match(/jobs\/view\/(\d+)/);if(m)ids.add(m[1]);});try{const u=new URL(location.href);['currentJobId','currentJobId'].forEach(k=>{const v=u.searchParams.get(k);if(v)ids.add(v);});}catch(e){}(document.body.innerHTML.match(/jobPosting:(\d{6,})/g)||[]).forEach(s=>ids.add(s.split(':')[1]));const links=[...ids].map(i=>`https://www.linkedin.com/jobs/view/${i}/`).join('\n');navigator.clipboard.writeText(links).then(()=>alert(`Copied ${ids.size} job link(s) to clipboard.\nPaste into INBOX.md, then tell Claude "inbox".`),()=>prompt('Copy these:',links));})();
```

## Use
1. On LinkedIn, run a job search (or open your saved-search / job-alerts results).
2. Scroll so the results you want are loaded on the page.
3. Click the **Grab Jobs → clipboard** bookmark.
4. It copies all job links; open `INBOX.md`, paste, save.
5. Tell Claude **"inbox"** → tailored CVs + cover letters.

## Notes
- Works on jobs **search results**, **saved searches**, **recommended jobs**, and single job pages.
- It only reads links already rendered on the page you're viewing — the same
  thing you can see. It does not log in, click, scroll, or call any API.
- If clipboard access is blocked, it falls back to a text box you can copy from.

## The other capture path: `save_open_urls.py`
This bookmarklet grabs job links **visible on one LinkedIn page** at a time
(paste into `INBOX.md` yourself). `../save_open_urls.py` (double-click
`../save_urls.command`) instead reads **every open Chrome tab across all
windows** and writes straight into `tracking/INBOX.md` itself — handy after a
browsing session where you opened a bunch of postings (from any site, not just
LinkedIn) in tabs to look at later. Both write to the same place and dedupe
against each other; use whichever fits the moment.
