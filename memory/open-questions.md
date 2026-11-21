# Open questions and undecided ideas

Move an item to [decisions.md](decisions.md) once it is decided, and delete it here.

## Waiting on the organizers
- Is reference data prepared before the event (the item catalog and truck tables) acceptable if we disclose it? Until answered, rebuild it today or disclose it in Pack-It-Up's README.
- Does the Managed Agents prize require a specific agent or model?
- Can the live demo use footage filmed in the judging room?

## Waiting on a person
- **Who owns `backend/catalog.py` and `data/item_catalog.csv`?** The plan gives them to George; the Track A session created first versions so ingestion could start. George should extend them rather than rewrite them. (Chris and George)
- **Living room media.** `data/Inputs/Living Room/` is empty. Is the home photo still coming? (Chris)

## Ideas proposed, not decided
- **Lifting guidance on unload steps:** tags such as "two-person lift" or "over 50 lb", using the catalog's `two_person` flag and weights. About 30 minutes in B8. Suggested as core.
- **Truck-mode reminder:** one checklist line on the final plan screen telling drivers to use a truck-aware nav setting. About 5 minutes. Check which apps really have a truck mode before naming one.
- **Route warnings:** low clearances and hills between the venue and Penn Station for the chosen truck's height. Stretch after 3 PM; needs an exterior-height column in `trucks.csv` and a data source we haven't picked.
