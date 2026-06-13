# Niva — Grammar Specification (v1)

_The formal grammar for `.niva` flows and the lexical rules a parser implements.
Closes Oscar **G5**. Normative for v1; the readable intro is in `01`/`03`._

---

## 1. Overview

A niva program is a `.niva` file (or a single inline flow string). It is a
sequence of **flows** and **`call`** statements, executed **procedurally**
top-to-bottom (`03-§4.1`). A **flow** is one or more **stages** joined by `|`. A
**stage** is a verb plus arguments.

## 2. Lexical structure

- **Encoding:** UTF-8.
- **Comments:** `#` to end of line (when not inside a quote).
- **Whitespace:** spaces/tabs separate tokens; otherwise insignificant.
- **Line breaks:** a flow may span multiple physical lines — a `|` at the end of a
  line (or the start of the next) **continues** the flow. One or more **blank
  lines** separate flows. A `call` statement is a single line.
- **Tokens:** `PIPE` (`|`), `WORD`, `NUMBER`, `DISTANCE`, `STRING`, `EQUALS`
  (`=` inside an option), `COMMENT`.

### 2.1 Values & quoting

- A **bare value** is a run of characters with no whitespace, `|`, or `#`, not
  beginning a quote — e.g. `100`, `EPSG:2262`, `city.gpkg`, `roads`, `@cats_pg`.
- **Single-** (`'…'`) and **double-quoted** (`"…"`) strings hold spaces/specials;
  `\` escapes the quote char and itself. Use them for paths with spaces and for
  expressions.
- **Expressions and SQL are a single quoted string.** They contain their own
  quotes, so the tokenizer treats the whole quoted blob as one value:
  `filter "\"ZONE\" = 'R1' and area($geometry) > 1000"`,
  `sql @db "SELECT … WHERE x = 'y'"`.
- A **`DISTANCE`** is a `NUMBER` immediately followed by an optional unit
  (`100`, `100m`, `0.5km`) — units and resolution per `03-§1.1`.

### 2.2 Stage tokens (after the verb)

| Token | Form | Meaning |
|-------|------|---------|
| option | `key=value` (no spaces around `=`) | a named parameter |
| flag | a bare word the verb declares as a flag | boolean `true` |
| positional | any other bare value / string / distance | consumed in the verb's declared order |

**Disambiguation rule:** option keys and flag names are per-verb and unique
(`07-§4`); the **first** token that is neither a known option nor a known flag is
the **next positional**.

## 3. Grammar (EBNF)

```ebnf
program     = { blank | comment | call | flow } ;
call        = "call" , value , NEWLINE ;
flow        = stage , { "|" , stage } ;          (* '|' may be wrapped by newlines *)
stage       = verb , { arg } ;
verb        = WORD ;
arg         = option | flag | value ;
option      = WORD , "=" , value ;
flag        = WORD ;                              (* validated vs the verb's flag set *)
value       = WORD | DISTANCE | STRING ;
DISTANCE    = NUMBER , [ unit ] ;
unit        = "m" | "km" | "cm" | "ft" | "yd" | "mi" | "nmi" | "deg" ;
STRING      = "'" , { char | "\\'" } , "'" | '"' , { char | '\\"' } , '"' ;
comment     = "#" , { char } , NEWLINE ;
blank       = NEWLINE ;
```

## 4. Parsing → binding

The parser emits, per stage, a `Stage{verb, positionals[], flags{}, options{}}`
(`02-§2`). The **registry** (`07`) binds these to a QGIS algorithm's parameters;
the **engine** threads the upstream layer into the verb's primary input and the
output to the next stage (`02-§2a`, `02-§3`).

Errors are reported by stage with a suggestion (`02-§6`):
- unknown verb → "unknown verb `bufer`; did you mean `buffer`?"
- unknown option/flag → list the verb's valid options/flags.
- too few positionals → name the missing argument from the verb spec.

## 5. Reserved words

- **Built-in verbs** — `load save add sql filter compute run find describe call` —
  are reserved; a registry alias may not shadow them (`07-§2`).
- **`as`** is a contextual keyword in `save <path> as <layer>` (`03-§2.5`).
- **`from`** is a contextual keyword in `sql "…" from <source>` (`03-§2.1`).
- **`@name`** denotes a saved QGIS connection (`02-§3.5`).

## 6. Examples

```
# one flow, wrapped across lines
load roads.gpkg
  | buffer 100m dissolve
  | clip city.gpkg
  | save roads_local.gpkg          # comment to EOL

# a second flow (blank line separates), with an expression and an option
load parcels.gpkg | filter "\"zone\" = 'R1'" | compute area_m2="$area" | save r1.gpkg

# a call and a DB read
call acquire.niva
sql @cats_pg "SELECT * FROM homes WHERE has_cat" | save targets.gpkg
```

## 7. Open (non-blocking) grammar questions

- Is `load` required to start a flow, or may a verb take a path directly
  (`buffer roads.gpkg 100m`)? — `00`/`03`.
- `.niva` flow separator: blank line (chosen) vs `;`. — `00`.
- Extras syntax in `run` (e.g. `requests[security]`) — passes through as a value.
