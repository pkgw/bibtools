# Bash completion setup for 'bib'. Modeled on git's but I don't know what I'm
# doing so that'll go well.

# These are just straight-up copied from Git. Documentation is omitted here.
__bib_reassemble_comp_words_by_ref ()
{
    local exclude i j first
    # Which word separators to exclude?
    exclude="${1//[^$COMP_WORDBREAKS]}"
    cword_=$COMP_CWORD
    if [ -z "$exclude" ]; then
        words_=("${COMP_WORDS[@]}")
        return
    fi
    # List of word completion separators has shrunk;
    # re-assemble words to complete.
    for ((i=0, j=0; i < ${#COMP_WORDS[@]}; i++, j++)); do
        # Append each nonempty word consisting of just
        # word separator characters to the current word.
        first=t
        while
          [ $i -gt 0 ] &&
          [ -n "${COMP_WORDS[$i]}" ] &&
          # word consists of excluded word separators
          [ "${COMP_WORDS[$i]//[^$exclude]}" = "${COMP_WORDS[$i]}" ]
        do
            # Attach to the previous token,
            # unless the previous token is the command name.
            if [ $j -ge 2 ] && [ -n "$first" ]; then
                ((j--))
            fi
            first=
            words_[$j]=${words_[j]}${COMP_WORDS[i]}
            if [ $i = $COMP_CWORD ]; then
                cword_=$j
            fi
            if (($i < ${#COMP_WORDS[@]} - 1)); then
                ((i++))
            else
                # Done.
                return
            fi
        done
        words_[$j]=${words_[j]}${COMP_WORDS[i]}
        if [ $i = $COMP_CWORD ]; then
            cword_=$j
        fi
    done
}

if ! type _get_comp_words_by_ref >/dev/null 2>&1; then
_get_comp_words_by_ref ()
{
    local exclude cur_ words_ cword_
    if [ "$1" = "-n" ]; then
        exclude=$2
        shift 2
    fi
    __bib_reassemble_comp_words_by_ref "$exclude"
    cur_=${words_[cword_]}
    while [ $# -gt 0 ]; do
        case "$1" in
            cur)
                cur=$cur_
                ;;
            prev)
                prev=${words_[$cword_-1]}
                ;;
            words)
                words=("${words_[@]}")
                ;;
            cword)
                cword=$cword_
                ;;
        esac
        shift
    done
}
fi


# Generates completion reply, appending a space to possible completion words,
# if necessary.
# It accepts 1 to 4 arguments:
# 1: List of possible completion words.
# 2: A prefix to be added to each possible completion word (optional).
# 3: Generate possible completion matches for this word (optional).
# 4: A suffix to be appended to each possible completion word (optional).
__bib_complete ()
{
    local cur_="${3-$cur}"

    case "$cur_" in
        --*=)
            ;;
        *)
            local c i=0 IFS=$' \t\n'
            for c in $1; do
                c="$c${4-}"
                if [[ $c == "$cur_"* ]]; then
                    case $c in
                        --*=*|*.) ;;
                        *) c="$c " ;;
                    esac
                    COMPREPLY[i++]="${2-}$c"
                fi
            done
            ;;
    esac
}


# bib-specific infrastructure!

_bib_group ()
{
    local i c=2 command
    while [ $c -lt $cword ]; do
	i="${words[c]}"
	case "$i" in
	    -*) ;;
	    *) command="$i" ; break ;;
	esac
	((c++))
    done

    if [ -z "$command" ]; then
	__bib_complete "$(bib _complete group_subcmds)"
	return
    fi

    if [ "$command" = add -o "$command" = rm ]; then
	if [ $cword -eq 3 ]; then
	    __bib_complete "$(bib _complete group "$cur")"
	else
	    __bib_complete "$(bib _complete pub "$cur")"
	fi
    elif [ "$command" = list ]; then
	__bib_complete "$(bib _complete group "$cur")"
    fi
}

__bib_main ()
{
    local cur words cword prev
    _get_comp_words_by_ref -n =: cur words cword prev

    local i c=1 command
    while [ $c -lt $cword ]; do
	i="${words[c]}"
	case "$i" in
	    -*) ;;
	    *) command="$i" ; break ;;
	esac
	((c++))
    done

    if [ -z "$command" ]; then
	case "$cur" in
	    -*) __bib_complete "--help" ;;
	    *) __bib_complete "$(bib _complete commands)" ;;
	esac
	return
    fi

    case "$command" in
	ads|apage|delete|edit|forgetpdf|info|jpage|pdfpath|read)
	    __bib_complete "$(bib _complete pub "$cur")" ; return ;;
    esac

    local completion_func="_bib_${command//-/_}"
    declare -f $completion_func >/dev/null && $completion_func
}

complete -o bashdefault -o default -o nospace -F __bib_main bib 2>/dev/null \
    || complete -o default -o nospace -F __bib_main bib
