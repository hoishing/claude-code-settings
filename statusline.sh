#!/bin/bash
# Claude Code statusline: Context % | 5h: % tokens (reset) | 7d: % (reset)
exec 2>/dev/null

input=$(cat)

tab=$(printf '\t')
parsed=$(printf '%s' "$input" | jq -r '[
  (.cwd // "" | tostring),
  (.model.display_name // "" | tostring),
  ((.context_window.current_usage.input_tokens // 0)
   + (.context_window.current_usage.cache_creation_input_tokens // 0)
   + (.context_window.current_usage.cache_read_input_tokens // 0) | tostring),
  (.context_window.context_window_size // 0 | tostring),
  (.rate_limits.five_hour.used_percentage // null | if . then (. | round | tostring) else "null" end),
  (.rate_limits.five_hour.resets_at // "" | tostring),
  (.rate_limits.five_hour.tokens_used // null | if . then tostring else "null" end),
  (.rate_limits.five_hour.tokens_limit // null | if . then tostring else "null" end),
  (.rate_limits.seven_day.used_percentage // null | if . then (. | round | tostring) else "null" end),
  (.rate_limits.seven_day.resets_at // "" | tostring)
] | @tsv')

IFS="$tab" read -r cwd model used_tokens window_size five_pct five_reset five_tok five_lim week_pct week_reset <<EOF
$parsed
EOF

RESET="\033[0m"
DIM="\033[2m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
BLUE="\033[94m"
MAGENTA="\033[95m"
WHITE="\033[97m"

# Shorten cwd and model
short_cwd=$(printf '%s' "$cwd" | sed "s|^$HOME|~|")
model_short=$(printf '%s' "$model" | sed 's/Claude //')

# Format large numbers: 1234567 -> 1.2M, 45678 -> 45.7K
fmt_tokens() {
  local n="$1"
  [ -z "$n" ] || [ "$n" = "null" ] && return
  if [ "$n" -ge 1000000 ] 2>/dev/null; then
    awk -v n="$n" 'BEGIN { printf "%.1fM", n/1000000 }'
  elif [ "$n" -ge 1000 ] 2>/dev/null; then
    awk -v n="$n" 'BEGIN { printf "%.0fK", n/1000 }'
  else
    printf "%s" "$n"
  fi
}

# Format seconds remaining as "4h23m" or "1d21h"
format_reset() {
  local ts="$1"
  [ -z "$ts" ] && return
  local epoch now diff
  epoch=$(printf '%s' "$ts" | tr -dc '0-9')
  [ -z "$epoch" ] && return
  now=$(date +%s)
  diff=$((epoch - now))
  [ "$diff" -le 0 ] && return
  local mins=$(( diff / 60 ))
  local hours=$(( mins / 60 ))
  local days=$(( hours / 24 ))
  if [ "$days" -ge 1 ]; then
    printf "%dd%dh" "$days" $(( hours % 24 ))
  elif [ "$hours" -ge 1 ]; then
    printf "%dh%dm" "$hours" $(( mins % 60 ))
  else
    printf "%dm" "$mins"
  fi
}

# Context %
ctx_pct=0
if [ "$window_size" -gt 0 ] 2>/dev/null; then
  ctx_pct=$(awk -v u="$used_tokens" -v t="$window_size" 'BEGIN { printf "%d", (u/t)*100 }')
fi
if [ "$ctx_pct" -ge 85 ] 2>/dev/null; then
  ctx_color="$RED"
elif [ "$ctx_pct" -ge 70 ] 2>/dev/null; then
  ctx_color="$YELLOW"
else
  ctx_color="$GREEN"
fi
context_part="${DIM}Context${RESET} ${ctx_color}${ctx_pct}%${RESET}"

# Usage color
usage_color() {
  local pct="$1"
  if [ "$pct" -ge 90 ] 2>/dev/null; then printf "%s" "$RED"
  elif [ "$pct" -ge 70 ] 2>/dev/null; then printf "%s" "$MAGENTA"
  else printf "%s" "$BLUE"
  fi
}

# 5h part
if [ "$five_pct" != "null" ] && [ -n "$five_pct" ]; then
  color=$(usage_color "$five_pct")
  reset_str=$(format_reset "$five_reset")
  tok_str=""
  if [ "$five_tok" != "null" ] && [ -n "$five_tok" ]; then
    used_fmt=$(fmt_tokens "$five_tok")
    if [ "$five_lim" != "null" ] && [ -n "$five_lim" ]; then
      lim_fmt=$(fmt_tokens "$five_lim")
      tok_str=" ${DIM}${used_fmt}/${lim_fmt}${RESET}"
    else
      tok_str=" ${DIM}${used_fmt}${RESET}"
    fi
  fi
  if [ -n "$reset_str" ]; then
    five_part="${DIM}5h:${RESET} ${color}${five_pct}%${RESET}${tok_str} ${DIM}(${reset_str})${RESET}"
  else
    five_part="${DIM}5h:${RESET} ${color}${five_pct}%${RESET}${tok_str}"
  fi
else
  five_part="${DIM}5h: --${RESET}"
fi

# 7d part
if [ "$week_pct" != "null" ] && [ -n "$week_pct" ]; then
  wcolor=$(usage_color "$week_pct")
  wreset_str=$(format_reset "$week_reset")
  if [ -n "$wreset_str" ]; then
    week_part="${DIM}7d:${RESET} ${wcolor}${week_pct}%${RESET} ${DIM}(${wreset_str})${RESET}"
  else
    week_part="${DIM}7d:${RESET} ${wcolor}${week_pct}%${RESET}"
  fi
else
  week_part="${DIM}7d: --${RESET}"
fi

printf "%b | %b | %b | %b | %b\n" "${GREEN}${short_cwd}${RESET}" "${DIM}${model_short}${RESET}" "$context_part" "$five_part" "$week_part"
