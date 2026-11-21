You are designing and writing the judging slide deck for Pack It Up, a hackathon project. You write all the copy and all the design. The facts you may use are in the brief below; the screenshots of the real app are attached as images, in the order listed under "Images".

Return one complete, self-contained HTML file and nothing else: no explanation, no Markdown fences.

## Format

- Exactly 8 slides, each a `<section class="slide" data-n="N">` (N = 1..8), in the brief's slide order.
- Each slide is designed at 1920×1080 CSS pixels and scaled to fit the browser window, letterboxed, keeping 16:9.
- One slide shows at a time. Right arrow, Space, Page Down or a click go forward; Left arrow or Page Up go back; Home and End jump. Show "N / 8" small in a corner.
- `#slide=N` in the URL opens slide N, and the hash updates as you move.
- Printing (`@media print`, `@page { size: 1920px 1080px; margin: 0 }`) puts every slide on its own page at full size, all visible.
- No external scripts. The only external resource allowed is Google Fonts (one family, with a system-font fallback so it still works offline).
- Images: only the files listed under "Images", by exactly those relative paths. Never draw or imitate app screenshots in HTML or CSS; show the real images. Keep each screenshot's aspect ratio; phone screenshots can sit in a simple phone outline.
- Text must be readable from the back of a room: body text at least 32px at the 1920×1080 design size, headlines much larger. At most about 40 words of copy per slide outside tables.

## Content rules

- Use only facts and numbers from the brief. Do not invent numbers, customers, quotes, prices or features.
- Say the caveats the brief requires on the "What we measured" slide, plainly.
- Name the Gemini model at each step where the brief names one.
- Slide 6 includes the line that this deck was made with Gemini 4 Carbon.
- Write like a person explaining their project to friends: short, concrete, no hype words ("revolutionary", "seamless", "cutting-edge", "unlock", "leverage").

## Design

Your own visual design. It should feel like a clean, modern Google product presentation: generous white space, a confident colour accent, clear hierarchy. Not a generic template.
