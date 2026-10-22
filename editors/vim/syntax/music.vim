" Vim syntax file
" Language:    Music DSL (.music)
" Maintainer:  music-dsl
" Latest Revision: 2026-10-22

if exists("b:current_syntax")
  finish
endif

syntax case match

" comments
syntax match musicComment /#.*/ contains=musicTodo
syntax keyword musicTodo TODO FIXME XXX NOTE

" track header: -- name: inst vol pan --
syntax match musicTrackHeader /^--.*--$/

" file-level directives
syntax match musicDirective /^\s*\(tempo\|name\|key\|time\|swing\|master\|arrange\|progression\|degrees\|label\|transpose\):/

" section definition
syntax match musicSection /^\s*%[A-Za-z_]\w*/

" jump label
syntax match musicLabel /^\s*\[[^\]]\+\]/

" @commands
syntax match musicAtCmd /@\%(jump\|done\|include\|pattern\|end\|steps\|arp\|drums\|gen\|coin\|call\)\>/
syntax match musicPatternCall /@[A-Za-z_]\w*/

" effects: reverb:0.4 filter:lp 800 ...
syntax match musicEffect /\<\%(reverb\|delay\|filter\|dist\|humanize\|vibrato\|tremolo\|portamento\|lfo\|sidechain\|swing\|adsr\|voice\)\s*:/

" dynamics
syntax keyword musicDynamic ppp pp p mp mf f ff fff sffz fp

" accents before pitches
syntax match musicAccent /[>+^][A-G][#b]/

" pitches and chords
syntax match musicNote /\%(^\|\s\)\@<=[A-G][#b]\d\{0,2}\d\{1,2}\|\%(^\|\s\)\@<=[A-G][#b]\?\d\{1,2}\>/
syntax match musicChord /\%(^\|\s\)\@<=[A-G][#b]\?\d\{0,2}\%(maj\|m\|dim\|aug\|sus\|add\|alt\|M\)\w*/

" rests
syntax match musicRest /\%(^\|\s\)\@<=\%(R\|rest\|_\)\%(\s\|$\)\@=/

" durations after a pitch
syntax match musicDuration /\%(^\|\s\)\@<=[whqestx]\.\+\>/ contains=musicDot
syntax match musicDot /\. containedin=musicDuration

" velocity override
syntax match musicVelocity /@\d*\.\?\d\+/

" repeat count
syntax match musicRepeat /\<x\d\+/

" volta endings
syntax match musicVolta /\[[12]\]\?/

" tuplet
syntax match musicTuplet /\<\d\+:\d\+\>/

" ties
syntax match musicTie /\%(^\|\s\)\@<=~\%(\s\|$\)\@=/

highlight default link musicComment      Comment
highlight default link musicTodo         Todo
highlight default link musicTrackHeader  Type
highlight default link musicDirective    PreProc
highlight default link musicSection      Label
highlight default link musicLabel        Label
highlight default link musicAtCmd        Statement
highlight default link musicPatternCall  Function
highlight default link musicEffect       Special
highlight default link musicDynamic      Constant
highlight default link musicAccent       SpecialChar
highlight default link musicNote         Number
highlight default link musicChord        Identifier
highlight default link musicRest         Constant
highlight default link musicDuration     Type
highlight default link musicDot          Type
highlight default link musicVelocity     Number
highlight default link musicRepeat       Repeat
highlight default link musicVolta        Repeat
highlight default link musicTuplet       Number
highlight default link musicTie          Operator

let b:current_syntax = "music"
