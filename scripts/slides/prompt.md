You are designing and writing the judging slide deck for Pack It Up, a hackathon project. You write all the copy and all the design. The facts you may use are in the brief below; the screenshots of the real app are attached as images, in the order listed under "Images".

Return one complete, self-contained HTML file and nothing else: no explanation, no Markdown fences.

## Format

- Exactly 8 slides, each a `<section class="slide" data-n="N">` (N = 1..8), in the brief's slide order.
- Each slide is designed at 1920×1080 CSS pixels and scaled to fit the browser window, letterboxed, keeping 16:9.
- One slide shows at a time. Right arrow, Space, Page Down or a click go forward; Left arrow or Page Up go back; Home and End jump. Show "N / 8" small in the top-right corner (never bottom-right: the QR badge lives there).
- `#slide=N` in the URL opens slide N, and the hash updates as you move.
- Printing (`@media print`, `@page { size: 1920px 1080px; margin: 0 }`) puts every slide on its own page at full size, all visible.
- No external scripts. The only external resource allowed is Google Fonts (one family, with a system-font fallback so it still works offline).
- Images: only the files listed under "Images", by exactly those relative paths. Never draw or imitate app screenshots in HTML or CSS; show the real images. Keep each screenshot's aspect ratio; phone screenshots can sit in a simple phone outline.
- Text must be readable from the back of a room: body text at least 30px at the 1920×1080 design size, headlines much larger. At most about 60 words of copy per slide outside tables.

## Content rules

- Use only facts and numbers from the brief. Do not invent numbers, customers, quotes, prices or features.
- Say the caveats the brief requires on the "What we measured" slide, plainly.
- Name the Gemini model at each step where the brief names one.
- Slide 6 includes the line that this deck was made with Gemini 4 Carbon.
- Write like a person explaining their project to friends: short, concrete, no hype words ("revolutionary", "seamless", "cutting-edge", "unlock", "leverage").

## The QR code (required, checked)

- Slide 1: the QR code is front and centre, large (about 520 to 600 px square) on a near-white card, with "Scan to try it" and the address under it.
- Slides 2 to 8: the same small QR badge on every slide, in exactly the same place and size: pinned to the bottom-right corner (`right: 64px; bottom: 64px`), about 220 px square, dark code on a near-white card with a visible border, and a short "Scan to try it" label just to its left. Slide content keeps clear of that corner (stop content at y 920 on the right side). Slide 8 may also show a large QR code in its layout, but keeps the corner badge too.
- The QR image always sits on a near-white background so a phone can read it, whatever the slide's background.

## Layout and density (reference: the team's earlier deck)

The first version of this deck had far too much white space and the parts were hard to tell apart. The team's earlier deck had the right density and layout; use its layout, not its look:

- Canvas 1920×1080 with 128 px margins (bottom 160 px on slides with the corner QR badge). Content fills the space inside the margins; no big empty areas.
- Each content slide: a small uppercase eyebrow line (about 24 px, accent colour), a headline (about 72 px), then the body.
- One type scale: about 144 / 72 / 44 / 30 / 24 px. Body text 30 px minimum; card and callout titles 44 px.
- "How it works": step cards in a row, each with a big step number (72 px), a 44 px title, a one-line 30 px body, and a filled pill naming the model (pills for Gemini models in the accent colour).
- Screenshot slides (3 to 6): screenshots large, side by side on the left in framed boxes with a 3 px border and rounded corners (phone screenshots about 380×620 px each; the laptop screenshots about 820 to 1000 px wide and 620 px tall, cropped from the top with `object-fit: cover; object-position: top`), and on the right three short callouts, each a 44 px title and one 30 px sentence.
- "What we measured": three or four big numbers (about 144 px, accent colour) each over a short 30 px label, with a heavy rule above each; the caveats underneath in 30 px, not tiny.
- Strong visual distinction: alternate slide backgrounds (a dark cover, light content slides, one or two slides on a second tone), cards and frames with clearly different fills or borders from the slide background, text contrast of at least 4.5:1. Nothing pale-grey on white.

## Theme and tone: yours

Choose the theme and the tone yourself, as Gemini: palette, typeface (one Google Fonts family, or two), shapes, accents and the voice of the copy. Make it feel like a modern Google product launch deck. Do not reuse the earlier deck's look: not its ink-navy, kraft-paper and orange palette, and not its fonts (Oswald, Public Sans).
