#!/bin/bash

# 讀取 Claude Code 傳入的 JSON 數據
read -r input

# 使用 jq 解析數據
# tokens.used: 當前會話已使用的 Token 總量
# tokens.percentage_used: 已使用的上下文視窗百分比
used_tokens=$(echo "$input" | jq -r '.tokens.used // 0')
percent=$(echo "$input" | jq -r '.tokens.percentage_used // 0')
model=$(echo "$input" | jq -r '.model.display_name')

# 格式化輸出 (支援 ANSI 顏色)
# \e[32m 為綠色, \e[33m 為黃色, \e[0m 為重置顏色
printf "\e[32m%s\e[0m | Tokens: \e[33m%s\e[0m | Context: \e[33m%.1f%%\e[0m" "$model" "$used_tokens" "$percent"
