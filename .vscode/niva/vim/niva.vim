" niva syntax file — text-pipeline grammar for QGIS geoprocessing
" Install: copy to ~/.vim/syntax/niva.vim (or :help syntax)
"
" Source: https://github.com/johnzastrow/niva
" Reference: niva/docs/guide/reference.md

if exists("b:current_syntax")
  finish
endif

syn match nivaComment "#.*$" contains=@Spell
syn region nivaString start='"' end='"' contains=nivaEscape
syn region nivaString start="'" end="'" contains=nivaEscape
syn match nivaEscape "\\\\." contained
syn match nivaPipe "|"
syn match nivaConnection "@[A-Za-z_][A-Za-z0-9_.-]*"
syn match nivaCrs "\<EPSG:\d\+\>"
syn match nivaDistance "\<\d\+\(\.\d\+\)\?\s*\(m\|km\|cm\|mm\|ft\|yd\|mi\|nmi\|deg\)\>"
syn match nivaNumber "\<\d\+\(\.\d\+\)\?\>"
syn match nivaOption "[A-Za-z_][A-Za-z0-9_-]*="
syn match nivaVariable "{[-A-Za-z0-9_./]\+}"
syn match nivaFlag "\<\(deep\|percent\|dissolve\|separate\|discard\|force\|relative\|absolute\|keep\|replace\|create\|append\|apply\|save\|fail\|drop\|set\|new\|info\|round\|flat\|square\)\>"

" Built-in verbs
syn keyword nivaBuiltin load save run filter sql split each call
syn keyword nivaBuiltin describe search docs show info catalog assess
syn keyword nivaBuiltin metadata style project notify email remove

" Alias verbs
syn keyword nivaAlias buffer clip intersect difference symdifference union
syn keyword nivaAlias dissolve reproject fixgeom centroid explode join
syn keyword nivaAlias zonalstats simplify smooth convexhull boundingbox
syn keyword nivaAlias minrect pointonsurface vertices densify subdivide
syn keyword nivaAlias offset swapxy forcerhr promote collect renamefield
syn keyword nivaAlias dropfields keepfields countpoints spatialjoin
syn keyword nivaAlias selectloc snap sample voronoi delaunay pointsalong
syn keyword nivaAlias warp clipraster hillshade slope aspect polygonize

hi def link nivaComment  Comment
hi def link nivaString   String
hi def link nivaEscape   SpecialChar
hi def link nivaPipe     Operator
hi def link nivaConnection Identifier
hi def link nivaCrs      Constant
hi def link nivaDistance  Number
hi def link nivaNumber   Number
hi def link nivaOption   Type
hi def link nivaVariable  Identifier
hi def link nivaFlag     Label
hi def link nivaBuiltin  Keyword
hi def link nivaAlias    Function

let b:current_syntax = "niva"
