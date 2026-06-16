"""The core alias set for v0.1 (docs/planning/04-mvp-scope.md verb set).

Every ``algorithm``/``param`` name here is a real QGIS ``native:*`` algorithm,
enumerated live from QGIS 4.0.3 (docs/planning/reference/*.tsv). The linter (07-§9,
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
        # Both default False (flags default off), preserving prior behaviour, but now
        # overridable: `reproject EPSG:2262 convert_curved transform_z`.
        flags={
            "convert_curved": Flag("CONVERT_CURVED_GEOMETRIES"),
            "transform_z": Flag("TRANSFORM_Z"),
        },
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
        "explode",
        "native:multiparttosingleparts",
        "Split multipart features into one feature per part.",
    ),
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
            # optional: write the input features that found no match to this file
            "unmatched": Option("NON_MATCHING", "string"),
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

    # ----------------------------------------------------------------- geometry
    Alias(
        "simplify",
        "native:simplifygeometries",
        "Reduce the number of vertices in geometries.",
        args=[Arg("tolerance", "TOLERANCE", "distance")],
        options={"method": Option("METHOD", "enum", "douglas",
                                  {"douglas": 0, "grid": 1, "area": 2})},
    ),
    Alias(
        "smooth",
        "native:smoothgeometry",
        "Round off sharp corners by adding vertices.",
        options={
            "iterations": Option("ITERATIONS", "int", "1"),
            "offset": Option("OFFSET", "number", "0.25"),
            "max_angle": Option("MAX_ANGLE", "number", "180"),
        },
    ),
    Alias("convexhull", "native:convexhull",
          "Wrap each feature (or the whole layer) in its convex hull."),
    Alias("boundingbox", "native:boundingboxes",
          "Replace each feature with its axis-aligned bounding box."),
    Alias("minrect", "native:orientedminimumboundingbox",
          "Replace each feature with its oriented minimum bounding rectangle."),
    Alias(
        "pointonsurface",
        "native:pointonsurface",
        "Place a point guaranteed to fall on each feature's surface.",
        flags={"all_parts": Flag("ALL_PARTS")},
    ),
    Alias("vertices", "native:extractvertices",
          "Extract every geometry vertex as a point layer."),
    Alias(
        "densify",
        "native:densifygeometriesgivenaninterval",
        "Add extra vertices along geometries at a fixed spacing.",
        args=[Arg("interval", "INTERVAL", "distance")],
    ),
    Alias(
        "subdivide",
        "native:subdivide",
        "Split complex geometries so no part exceeds a vertex budget.",
        options={"max_nodes": Option("MAX_NODES", "int", "256")},
    ),
    Alias(
        "offset",
        "native:offsetline",
        "Create a line parallel to the input at a given distance.",
        args=[Arg("distance", "DISTANCE", "distance")],
        options={
            "segments": Option("SEGMENTS", "int", "8"),
            "join": Option("JOIN_STYLE", "enum", "round", {"round": 0, "miter": 1, "bevel": 2}),
            "miter": Option("MITER_LIMIT", "number", "2"),
        },
    ),
    Alias("swapxy", "native:swapxy", "Swap the X and Y coordinates of geometries."),
    Alias("forcerhr", "native:forcerhr",
          "Reorder polygon rings to follow the right-hand rule."),

    # -------------------------------------------------------------- attributes
    Alias("promote", "native:promotetomulti",
          "Promote singlepart features to multipart."),
    Alias(
        "collect",
        "native:collect",
        "Combine geometries into multipart features (optionally grouped by a field).",
        args=[Arg("field", "FIELD", "field", required=False)],
    ),
    Alias(
        "renamefield",
        "native:renametablefield",
        "Rename an attribute field.",
        args=[Arg("field", "FIELD", "field"), Arg("name", "NEW_NAME", "string")],
    ),
    Alias(
        "dropfields",
        "native:deletecolumn",
        "Remove one or more attribute fields (comma-separated).",
        args=[Arg("fields", "COLUMN", "fields")],
    ),
    Alias(
        "keepfields",
        "native:retainfields",
        "Keep only the listed attribute fields (comma-separated).",
        args=[Arg("fields", "FIELDS", "fields")],
    ),
    Alias(
        "countpoints",
        "native:countpointsinpolygon",
        "Count points falling inside each polygon.",
        primary_input="POLYGONS",
        options={
            "points": Option("POINTS", "layer", required=True),
            "field": Option("FIELD", "string", "NUMPOINTS"),
            "weight": Option("WEIGHT", "field"),
            "classfield": Option("CLASSFIELD", "field"),
        },
    ),

    # ------------------------------------------------------------- overlay/relate
    Alias(
        "union",
        "native:union",
        "Overlay two layers, keeping all parts of both (self-union if no overlay).",
        args=[Arg("overlay", "OVERLAY", "layer", required=False)],
    ),
    Alias(
        "symdifference",
        "native:symmetricaldifference",
        "Keep the parts of each layer NOT shared with the other.",
        args=[Arg("overlay", "OVERLAY", "layer")],
    ),
    Alias(
        "spatialjoin",
        "native:joinattributesbylocation",
        "Join attributes from another layer by spatial relationship.",
        options={
            "with": Option("JOIN", "layer", required=True),
            "predicate": Option("PREDICATE", "enum", "intersect",
                                {"intersect": 0, "contain": 1, "equal": 2, "touch": 3,
                                 "overlap": 4, "within": 5, "cross": 6}),
            "method": Option("METHOD", "enum", "one-to-many",
                             {"one-to-many": 0, "first": 1, "largest": 2}),
            "fields": Option("JOIN_FIELDS", "fields"),
            "prefix": Option("PREFIX", "string"),
        },
        flags={"discard": Flag("DISCARD_NONMATCHING")},
    ),
    Alias(
        "selectloc",
        "native:extractbylocation",
        "Keep features that match a spatial relationship to another layer.",
        args=[Arg("against", "INTERSECT", "layer")],
        options={"predicate": Option("PREDICATE", "enumlist", "intersect",
                                     {"intersect": 0, "contain": 1, "disjoint": 2,
                                      "equal": 3, "touch": 4, "overlap": 5,
                                      "within": 6, "cross": 7})},
    ),

    # ------------------------------------------------------------------ selection
    Alias(
        "snap",
        "native:snapgeometries",
        "Snap geometries to a reference layer within a tolerance.",
        args=[Arg("reference", "REFERENCE_LAYER", "layer"),
              Arg("tolerance", "TOLERANCE", "distance")],
        options={"behavior": Option("BEHAVIOR", "enum", "align",
                                    {"align": 0, "closest": 1, "align-keep": 2,
                                     "closest-keep": 3, "ends-align": 4, "ends-closest": 5,
                                     "ends-only": 6, "anchor": 7})},
    ),
    Alias(
        "sample",
        "native:randomextract",
        "Extract a random subset of features.",
        args=[Arg("number", "NUMBER", "int")],
        options={"method": Option("METHOD", "enum", "count",
                                  {"count": 0, "percent": 1})},
    ),

    # ------------------------------------------------------------------- creation
    Alias(
        "voronoi",
        "native:voronoipolygons",
        "Build Voronoi (Thiessen) polygons around input points.",
        options={"buffer": Option("BUFFER", "number", "0")},
    ),
    Alias("delaunay", "native:delaunaytriangulation",
          "Build a Delaunay triangulation from input points."),
    Alias(
        "pointsalong",
        "native:pointsalonglines",
        "Place points along lines at a fixed spacing.",
        args=[Arg("distance", "DISTANCE", "distance")],
        options={"start": Option("START_OFFSET", "distance"),
                 "end": Option("END_OFFSET", "distance")},
    ),

    # --------------------------------------------------------------------- raster
    # NOTE: raster verbs default CREATION_OPTIONS to lossless DEFLATE + tiling so
    # intermediate/written rasters aren't left uncompressed (and far larger than their
    # inputs). The final product's compression is governed by `save` (which also picks
    # a data-type-aware PREDICTOR); for custom options use `run gdal:* CREATION_OPTIONS=…`.
    Alias(
        "warp",
        "gdal:warpreproject",
        "Reproject a raster to a target CRS.",
        args=[Arg("target_crs", "TARGET_CRS", "crs")],
        options={
            "source_crs": Option("SOURCE_CRS", "crs"),
            "resampling": Option("RESAMPLING", "enum", "nearest",
                                 {"nearest": 0, "bilinear": 1, "cubic": 2, "cubicspline": 3,
                                  "lanczos": 4, "average": 5, "mode": 6, "max": 7, "min": 8,
                                  "median": 9, "q1": 10, "q3": 11}),
            "nodata": Option("NODATA", "number"),
            "resolution": Option("TARGET_RESOLUTION", "number"),
        },
        forced={"CREATION_OPTIONS": "COMPRESS=DEFLATE|TILED=YES"},
    ),
    Alias(
        "clipraster",
        "gdal:cliprasterbymasklayer",
        "Clip a raster to the shape of a mask layer.",
        args=[Arg("mask", "MASK", "layer")],
        options={"nodata": Option("NODATA", "number")},
        forced={"CREATION_OPTIONS": "COMPRESS=DEFLATE|TILED=YES"},
    ),
    Alias(
        "hillshade",
        "native:hillshade",
        "Compute a shaded-relief (hillshade) raster from a DEM.",
        options={
            "z_factor": Option("Z_FACTOR", "number", "1"),
            "azimuth": Option("AZIMUTH", "number", "300"),
            "altitude": Option("V_ANGLE", "number", "40"),
        },
        forced={"CREATION_OPTIONS": "COMPRESS=DEFLATE|TILED=YES"},
    ),
    Alias(
        "slope",
        "gdal:slope",
        "Compute a slope raster from a DEM.",
        options={"band": Option("BAND", "int", "1"), "scale": Option("SCALE", "number", "1")},
        flags={"percent": Flag("AS_PERCENT")},
        forced={"CREATION_OPTIONS": "COMPRESS=DEFLATE|TILED=YES"},
    ),
    Alias(
        "aspect",
        "gdal:aspect",
        "Compute an aspect raster from a DEM.",
        options={"band": Option("BAND", "int", "1")},
        flags={"trig": Flag("TRIG_ANGLE"), "zero_flat": Flag("ZERO_FLAT")},
        forced={"CREATION_OPTIONS": "COMPRESS=DEFLATE|TILED=YES"},
    ),
    Alias(
        "polygonize",
        "gdal:polygonize",
        "Convert a raster into vector polygons (raster → vector).",
        options={"band": Option("BAND", "int", "1"), "field": Option("FIELD", "string", "DN")},
        flags={"eight": Flag("EIGHT_CONNECTEDNESS")},
    ),
]
