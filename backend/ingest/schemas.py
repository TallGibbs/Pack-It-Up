"""JSON schemas for model output. Kept flat (no $ref, oneOf or additionalProperties)
so any provider's structured-output mode accepts them."""

MOVE_CLASSES = ["movable", "fixture", "personal_belonging", "small_loose"]
MATERIALS = ["upholstered", "wood_solid", "wood_composite", "metal", "glass", "stone", "plastic", "electronics", "mixed"]
CONTAINER_KINDS = ["closet", "kitchen_cabinet", "bookshelf", "dresser_drawers", "pantry", "bathroom_cabinet", "desk",
                   "toy_storage", "garage_shelving", "open_surfaces", "other"]
CONTENTS = ["clothes_hanging", "clothes_folded", "books", "dishes_glassware", "pots_pans", "pantry_food", "linens",
            "toiletries", "papers_office", "toys", "tools", "decor", "mixed"]
FULLNESS = ["empty", "quarter", "half", "three_quarters", "full", "not_visible"]

_box = {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4,
        "description": "[ymin, xmin, ymax, xmax] on a 0-1000 scale"}

PERCEPTION_SCHEMA = {
    "type": "object",
    "required": ["room_guess", "scale_refs", "items", "containers", "uncertain"],
    "properties": {
        "room_guess": {"type": "string"},
        "scale_refs": {"type": "array", "items": {"type": "string"}},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label", "catalog_id", "quantity", "move_class", "est_dims_in", "dims_basis", "material",
                             "est_weight_lb", "fragile", "must_stay_upright", "disassemble", "two_person", "stackable",
                             "stack_count", "evidence", "partially_visible", "confidence"],
                "properties": {
                    "label": {"type": "string"},
                    "catalog_id": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1},
                    "move_class": {"type": "string", "enum": MOVE_CLASSES},
                    "est_dims_in": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 3, "maxItems": 3,
                                    "description": "[length, width, height] in inches, one unit"},
                    "dims_basis": {"type": "string"},
                    "material": {"type": "string", "enum": MATERIALS},
                    "est_weight_lb": {"type": "number", "minimum": 0},
                    "fragile": {"type": "boolean"},
                    "must_stay_upright": {"type": "boolean"},
                    "disassemble": {"type": "boolean"},
                    "two_person": {"type": "boolean"},
                    "stackable": {"type": "boolean"},
                    "stack_count": {"type": "integer", "minimum": 1},
                    "evidence": {
                        "type": "object",
                        "required": ["box_2d"],
                        "properties": {"timestamp_s": {"type": "number", "minimum": 0}, "box_2d": _box},
                    },
                    "partially_visible": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "containers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label", "kind", "contents", "fullness", "size", "est_item_count"],
                "properties": {
                    "label": {"type": "string"},
                    "kind": {"type": "string", "enum": CONTAINER_KINDS},
                    "contents": {"type": "string", "enum": CONTENTS},
                    "fullness": {"type": "string", "enum": FULLNESS},
                    "size": {"type": "string", "enum": ["small", "medium", "large"]},
                    "est_item_count": {"type": "integer", "minimum": 0,
                                       "description": "rough count of loose items, for open_surfaces"},
                    "evidence": {
                        "type": "object",
                        "properties": {"timestamp_s": {"type": "number", "minimum": 0}, "box_2d": _box},
                    },
                },
            },
        },
        "uncertain": {"type": "array", "items": {"type": "string"}},
    },
}
