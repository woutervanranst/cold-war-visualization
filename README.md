# The Cold War — a narrative chart

An interactive, xkcd-style [narrative chart](https://xkcd.com/657/) of Odd Arne Westad's
*The Cold War: A World History* (Basic Books, 2017).

**Live:** https://wouteronarchitecture.com/cold-war-visualization/

- **Countries** view: each line is a country; the pale bands are the camps it belonged to
  (the West, the Soviet camp, the non-aligned world, colonies, Communists on their own, the Axis).
  Lines cross between bands when a country changes sides.
- **Leaders** view: each line is a leader, running inside their country's band while in power;
  lines pinch together where leaders met or clashed (Yalta, Bandung, Nixon in Beijing, …).
- **Main cast / Full cast**: the main cast is the 20 countries and 22 leaders the book leans on
  most (index references plus the events they take part in, major events counting triple); the
  full cast adds everyone else. Anyone you search for is added back in.
- Hover for details (every note cites chapter and page), click a line to pin it, scroll or pinch to
  zoom, pick a chapter to see what it covers, search for a name, or open the list of events.
- Time before 1945 and after 1991 is squeezed so the Cold War itself gets most of the width.

The whole page is one hand-written `index.html` (D3 from a CDN, no build step) reading
`data/coldwar.json`. Add `?view=leaders` and/or `?cast=main` to a link to open it that way.

## How the data was made

The data is derived from the book, but the repo contains no book text: only facts, short notes
paraphrased in my own words, and chapter/page references to the print edition.

1. `tools/extract_epub.py <book.epub>` turns the epub into plain text with `[p.N]` page markers and
   parses the index, into `work/` (gitignored).
2. `tools/roster.json` picks the ~40 countries and ~55 leaders (weighted by index references) and
   defines the bands and regions.
3. Each chapter was read by an AI assistant (Claude) and turned into `work/extract/chNN.json`
   (events, alignment evidence, leader tenures), then spot-checked against the cited pages. `python3 tools/build_data.py --check work/extract/*.json` validates those files,
   including a check that no note repeats 8 or more consecutive words of the book.
4. `tools/timelines.json` holds the curated band history of each country and the terms of each
   leader.
5. `python3 tools/build_data.py` merges duplicate events across chapters, maps the index onto
   chapters for the chapter lens, validates everything, and writes `data/coldwar.json`.

Rebuilding needs your own copy of the epub (steps 1 and 5); the site itself only needs
`data/coldwar.json`.

## Running locally

```sh
python3 -m http.server 8000   # then open http://localhost:8000
```

## Credits

- Book: Odd Arne Westad, *The Cold War: A World History* (Basic Books, 2017).
- Idea: Randall Munroe, [xkcd 657 "Movie Narrative Charts"](https://xkcd.com/657/).
- Font: [xkcd Script](https://github.com/ipython/xkcd-font) by the IPython project,
  CC BY-NC 3.0.
- Built with [D3](https://d3js.org/).
