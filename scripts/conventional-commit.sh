#!/usr/bin/env bash
# Check that a commit message file or subject string follows Conventional Commits.
set -euo pipefail

readonly ALLOWED_TYPES='feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert'

usage() {
    cat <<'EOF'
Check that a commit subject follows Conventional Commits

Usage: conventional-commit.sh [FLAGS] [FILE]

Arguments:
  [FILE]  Commit message file whose first line is checked

Flags:
  -s, --subject <TEXT>  Check TEXT directly instead of reading a file
  -h, --help            Print help

Examples:
    $ conventional-commit.sh .git/COMMIT_EDITMSG

    $ conventional-commit.sh -s "feat(etl): add u-hoke-sein extractor"
EOF
}

usage_error() {
    printf 'conventional-commit.sh: error: %s\n\nUsage: conventional-commit.sh [FLAGS] [FILE]\n\nFor more information, try '\''--help'\''.\n' "$1" >&2
    exit 2
}

is_exempt_subject() {
    case "$1" in
    "Merge "* | "Revert "* | "fixup! "* | "squash! "*) return 0 ;;
    *) return 1 ;;
    esac
}

validate_subject() {
    local subject="$1"
    if is_exempt_subject "${subject}"; then
        return 0
    fi
    if ! printf '%s\n' "${subject}" | grep -qE "^(${ALLOWED_TYPES})(\([a-z0-9._/-]+\))?!?: [^ ].{0,100}\$"; then
        printf 'Commit message must look like: <type>(<optional scope>): <description>\n' >&2
        printf '  types: %s\n' "${ALLOWED_TYPES//|/ }" >&2
        printf '  got:   %s\n' "${subject}" >&2
        return 1
    fi
}

main() {
    local mode=""
    local target=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
        -h | --help)
            usage
            exit 0
            ;;
        -s | --subject)
            [[ $# -ge 2 ]] || usage_error "missing value for $1"
            mode="subject"
            target="$2"
            shift 2
            ;;
        --subject=*)
            mode="subject"
            target="${1#*=}"
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            usage_error "unknown flag: $1"
            ;;
        *)
            [[ -z "${mode}" ]] || usage_error "unexpected argument: $1"
            mode="file"
            target="$1"
            shift
            ;;
        esac
    done

    if [[ $# -gt 0 ]]; then
        [[ -z "${mode}" && $# -eq 1 ]] || usage_error "unexpected positional arguments"
        mode="file"
        target="$1"
    fi

    if [[ "${mode}" == "file" ]]; then
        [[ -f "${target}" ]] || usage_error "file not found: ${target}"
        target="$(head -n 1 "${target}")"
    elif [[ "${mode}" != "subject" ]]; then
        usage_error "expected a commit message file or --subject <TEXT>"
    fi

    validate_subject "${target}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
