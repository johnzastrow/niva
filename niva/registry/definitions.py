"""The core alias set for v0.1 (planning/04-mvp-scope.md verb set).

Every ``algorithm``/``param`` name here is a real QGIS ``native:*`` algorithm,
enumerated live from QGIS 4.0.3 (planning/reference/*.tsv). The linter (07-§9,
later increment) re-checks these against the host's installed providers so the set
fails loud, not silent, when an algorithm or parameter moves.

Built-in verbs (``load`` / ``save`` / ``add`` / ``sql`` / ``filter`` / ``compute``
/ ``run`` / ``find`` / ``describe`` / ``call``) are **not** aliases — the engine
handles them directly — so they are deliberately absent from this list.
"""

from .model import Alias, Arg, Flag, Option

CORE = [
    Alias(
        "buffer",
        "native:buffer",
        "Expand (or shrink) geometries by a distance.",
        args=[Arg("distance", "DISTANCE", "distance")],
        options={
            "segments": Option("SEGMENTS", "int", "5"),
            "cap": Option("END_CAP_STYLE", "enum", "round", {"round": 0, "flat": 1, "square": 2}),
            "join": Option("JOIN_STYLE", "enum", "round", {"round": 0, "miter": 1, "bevel": 2}),
            "miter": Option("MITER_LIMIT", "number", "2"),
        },
        flags={"dissolve": Flag("DISSOLVE"), "separate": Flag("SEPARATE_DISJOINT")},
    ),
    Alias(
        "clip",
        "native:clip",
        "Clip a layer to the parts that fall inside an overlay.",
        args=[Arg("overlay", "OVERLAY", "layer")],
    ),
    Alias(
        "intersect",
        "native:intersection",
        "Keep the overlapping parts of two layers (and merge their attributes).",
        args=[Arg("overlay", "OVERLAY", "layer")],
    ),
    Alias(
        "difference",
        "native:difference",
        "Keep the parts of the input that fall outside an overlay.",
        args=[Arg("overlay", "OVERLAY", "layer")],
    ),
    Alias(
        "dissolve",
        "native:dissolve",
        "Merge features into one (optionally grouped by a field).",
        args=[Arg("field", "FIELD", "field", required=False)],
        flags={"separate": Flag("SEPARATE_DISJOINT")},
    ),
    Alias(
        "reproject",
        "native:reprojectlayer",
        "Reproject a layer to a target CRS.",
        args=[Arg("target_crs", "TARGET_CRS", "crs")],
        options={"operation": Option("OPERATION", "string")},
        forced={"CONVERT_CURVED_GEOMETRIES": False},
    ),
    Alias(
        "filter",
        "native:extractbyexpression",
        "Keep only the features matching an expression.",
        args=[Arg("expression", "EXPRESSION", "expression")],
    ),
    Alias("fix", "native:fixgeometries", "Repair invalid geometries."),
    Alias("centroid", "native:centroids", "Replace each feature with its centroid point."),
    Alias(
        "join",
        "native:joinattributestable",
        "Join attributes from another table by matching a field value.",
        options={
            "with": Option("INPUT_2", "layer", required=True),
            "field": Option("FIELD", "field", required=True),
            "field2": Option("FIELD_2", "field", required=True),
            "fields": Option("FIELDS_TO_COPY", "fields"),
            "prefix": Option("PREFIX", "string"),
            "method": Option("METHOD", "enum", "one-to-one", {"one-to-many": 0, "one-to-one": 1}),
        },
        flags={"discard": Flag("DISCARD_NONMATCHING")},
    ),
    Alias(
        "zonalstats",
        "native:zonalstatisticsfb",
        "Summarise raster values within each polygon zone.",
        primary_input="INPUT",
        options={
            "band": Option("RASTER_BAND", "int", "1"),
            "raster": Option("INPUT_RASTER", "raster", required=True),
            "stats": Option(
                "STATISTICS",
                "enumlist",
                "count,sum,mean",
                {
                    "count": 0, "sum": 1, "mean": 2, "median": 3, "stdev": 4, "min": 5,
                    "max": 6, "range": 7, "minority": 8, "majority": 9, "variety": 10,
                    "variance": 11,
                },
            ),
            "prefix": Option("COLUMN_PREFIX", "string", "_"),
        },
    ),
]
