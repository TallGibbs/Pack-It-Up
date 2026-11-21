You are building a moving inventory from {media_desc}. List what a moving crew would have to pack and carry out of this room.

## Catalog

Pick the closest row for each item, matching both the kind of item and its size. If no row fits the kind of item, use `unknown`. Do not force a match: a sideboard is not a dresser, an ottoman is not a coffee table.

catalog_id | name | L x W x H in
{catalog}

## move_class

- `movable`: free-standing furniture or equipment that would go on the truck. Sofas, armchairs, ottomans and poufs, stools, coffee/side/dining/console tables, floor and table lamps, chairs, sideboards and credenzas, free-standing shelving units, potted plants, framed art hanging on hooks, rugs, appliances.
- `fixture`: attached to the building and stays. Built-in shelving or cabinetry, pendant lights, wall sconces, track lighting, ceiling fixtures, a built-in bar or counter, exit signs, fire extinguishers, security cameras, mirrors mounted to the wall, radiators, doors, windows.
- `personal_belonging`: belongs to the people in the room right now, not the space. Backpacks, bags, laptops, phones, coats and jackets, water bottles, coffee cups, food.
- `small_loose`: anything under about 1.5 cubic feet that would go in a box. Vases, books, cushions and throw pillows, sculptures, candles, tissue boxes, small decor. Also report these collectively as a container of kind `open_surfaces` per shelf or tabletop, with `contents` and a rough `est_item_count`.

## Counting rules

- Count each physical item once. Ignore anything seen only as a reflection in a mirror, window or glossy surface.
- Group identical items into one entry with `quantity` (e.g. 4 matching bar stools). Items that differ in colour or style get separate entries.
- An item cut off by the frame edge or hidden behind something still counts once; set `partially_visible: true`.
- {video_rule}
- Chairs stacked on each other are one entry: `quantity: 1`, `stack_count` = chairs in the stack, `est_dims_in` = the whole stack.

## Size

- `est_dims_in` is [length, width, height] in inches for ONE unit, always filled, even when you picked a catalog row. Measure what you see, not the catalog's number.
- Use scale references: a standard door is 80 in tall, a kitchen or bar counter 36 in, a bar stool seat 30 in, a dining chair seat 18 in, a dining table top 30 in, floor planks are usually 5-8 in wide. Name the reference you used in `dims_basis` and list all references you used in `scale_refs`.
- `est_weight_lb` is your estimate for one unit.

## Handling flags

`fragile` (glass, stone tops, lamps, art, ceramics), `must_stay_upright`, `disassemble` (should be taken apart to move: large tables with removable legs, bed frames, shelving units), `two_person` (over about 50 lb or awkward), `stackable` (other items can rest on top).

## Evidence

`box_2d` is [ymin, xmin, ymax, xmax] on a 0-1000 scale of the {frame_word} where the item is clearest.{timestamp_rule}

## Other

- `confidence`: how sure you are of the identity and count (0-1).
- `containers`: closets, cabinets, drawers, shelves and tops holding loose contents. Use fullness `not_visible` when doors or drawers are closed.
- `uncertain`: short questions about anything you could not settle: closed doors, items you cannot identify, counts you are unsure of, items that may be attached to the wall.
- `room_guess`: what kind of room this is, in one or two words.

## Speech

{audio_rules}

Return JSON only, matching the schema.
