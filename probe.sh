#!/usr/bin/env bash
# Probe each linbpq node's NETROM "Nodes" page and count how many other
# Q* aliases it has learned about. Useful for watching convergence.
set -u
nodes=(QA0ABN QA0ABS QA0BBS QA0HUB QB0BRI QB0BBS QB0HUB QC0CAM QC0CAS QC0HUB QD0DUR QD0DUS QD0CHT QD0HUB QE0EXE QE0EXS QE0BBS QE0HUB)
host_port_base=18000
expected=$(( ${#nodes[@]} - 1 ))

i=0
total_known=0
for n in "${nodes[@]}"; do
    i=$((i+1))
    port=$((host_port_base + i))
    page=$(curl -s --max-time 3 "http://localhost:$port/Node/Nodes.html" || echo "")
    # BPQ displays Nodes as ALIAS:CALL (e.g. CAMHUB:QC0HUB-7)
    entries=$(printf '%s' "$page" | grep -oE '[A-Z]{3,6}:Q[A-E]0[A-Z]{3}-[0-9]+' | sort -u)
    if [ -z "$entries" ]; then
        others=0
    else
        others=$(printf '%s\n' "$entries" | grep -vc ":${n}-7$" || true)
    fi
    total_known=$(( total_known + others ))
    bar=$(printf '%*s' "$others" '' | tr ' ' '#')
    printf '  %-7s  %2d / %d  %s\n' "$n" "$others" "$expected" "$bar"
done
printf '\n  total %s discovered across all nodes (max %s)\n' "$total_known" "$(( ${#nodes[@]} * expected ))"
