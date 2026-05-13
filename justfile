# Context Climate — Development Commands

set dotenv-load
set dotenv-override := true  # .env wins over inherited empty/stale shell vars (e.g. ANTHROPIC_API_KEY="" from parent CLIs)

# Ports (loaded from .env via dotenv-load)
mcp_port := env("MCP_PORT")
app_port := env("APP_PORT")
root_path:= env("ROOT_PATH")
pid_dir  := ".pids"
log_dir  := ".logs"

# Show available commands
default:
    @just --list

# Start services (all, or one: just start fastmcp|chainlit|postgres)
start svc="all":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p {{pid_dir}} {{log_dir}}

    fmt() { printf "%s %-12s %s\n" "$1" "$2" "$3"; }

    # Cross-platform: get PID listening on a port (Linux ss / macOS lsof)
    pid_on_port() {
        local port="$1"
        if command -v ss > /dev/null 2>&1; then
            ss -tlnp 2>/dev/null | grep ":${port} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1
        elif command -v lsof > /dev/null 2>&1; then
            lsof -ti ":${port}" -sTCP:LISTEN 2>/dev/null | head -1
        fi
    }

    # Check if a port is in use
    port_in_use() {
        local pid=$(pid_on_port "$1")
        [ -n "$pid" ]
    }

    # Wait for a port to have a listener and return its PID
    resolve_pid() {
        local port="$1" max_wait="${2:-15}" i=0
        while [ $i -lt $max_wait ]; do
            local pid=$(pid_on_port "$port")
            if [ -n "$pid" ]; then echo "$pid"; return 0; fi
            sleep 1; i=$((i + 1))
        done
        return 1
    }

    start_postgres() {
        if docker compose ps --status running 2>/dev/null | grep -q postgres; then
            fmt "🐘" "PostgreSQL" "already running"; return
        fi
        fmt "🐘" "PostgreSQL" "starting..."
        docker compose up -d --wait > /dev/null 2>&1
        fmt "🐘" "PostgreSQL" "✅ running"
    }

    start_fastmcp() {
        local pidfile="{{pid_dir}}/mcp.pid"
        if [ -f "$pidfile" ] && kill -0 $(cat "$pidfile") 2>/dev/null; then
            fmt "⚡" "FastMCP" "already running (PID $(cat "$pidfile"))"; return
        fi
        rm -f "$pidfile"
        if port_in_use {{mcp_port}}; then
            fmt "⚡" "FastMCP" "❌ port {{mcp_port}} in use (PID $(pid_on_port {{mcp_port}}))"
            echo "   Fix: just stop fastmcp"; exit 1
        fi
        fmt "⚡" "FastMCP" "starting..."
        MCP_TRANSPORT=streamable-http MCP_PORT={{mcp_port}} \
            nohup uv run python -m mcp_server.server > {{log_dir}}/mcp.log 2>&1 &
        local real_pid=$(resolve_pid {{mcp_port}} 20)
        if [ -n "$real_pid" ]; then
            echo "$real_pid" > "$pidfile"
            fmt "⚡" "FastMCP" "✅ running (PID $real_pid)"
        else
            fmt "⚡" "FastMCP" "❌ failed to start"
            tail -10 {{log_dir}}/mcp.log 2>/dev/null
            rm -f "$pidfile"; exit 1
        fi
    }

    start_chainlit() {
        local pidfile="{{pid_dir}}/app.pid"
        if [ -f "$pidfile" ] && kill -0 $(cat "$pidfile") 2>/dev/null; then
            fmt "🌐" "Chainlit" "already running (PID $(cat "$pidfile"))"; return
        fi
        rm -f "$pidfile"
        if port_in_use {{app_port}}; then
            fmt "🌐" "Chainlit" "❌ port {{app_port}} in use (PID $(pid_on_port {{app_port}}))"
            echo "   Fix: just stop chainlit"; exit 1
        fi
        fmt "🌐" "Chainlit" "starting..."
        root_path_args=()
        if [ -n "{{root_path}}" ] && [ "{{root_path}}" != "/" ]; then
            root_path_args=(--root-path "{{root_path}}")
        fi
        nohup uv run chainlit run app/chat.py --port {{app_port}} ${root_path_args[@]+"${root_path_args[@]}"} --headless > {{log_dir}}/app.log 2>&1 &
        local real_pid=$(resolve_pid {{app_port}} 20)
        if [ -n "$real_pid" ]; then
            echo "$real_pid" > "$pidfile"
            fmt "🌐" "Chainlit" "✅ running (PID $real_pid)"
        else
            fmt "🌐" "Chainlit" "❌ failed to start"
            tail -10 {{log_dir}}/app.log 2>/dev/null
            rm -f "$pidfile"; exit 1
        fi
    }

    case "{{svc}}" in
        all)      start_postgres && start_fastmcp && start_chainlit ;;
        postgres) start_postgres ;;
        fastmcp)  start_fastmcp ;;
        chainlit) start_chainlit ;;
        *)        echo "Unknown service: {{svc}}. Use: postgres, fastmcp, chainlit" && exit 1 ;;
    esac

# Stop services (all, or one: just stop fastmcp|chainlit|postgres)
stop svc="all":
    #!/usr/bin/env bash
    set -uo pipefail

    fmt() { printf "%s %-12s %s\n" "$1" "$2" "$3"; }

    # Cross-platform: get PID listening on a port (Linux ss / macOS lsof)
    pid_on_port() {
        local port="$1"
        if command -v ss > /dev/null 2>&1; then
            ss -tlnp 2>/dev/null | grep ":${port} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1
        elif command -v lsof > /dev/null 2>&1; then
            lsof -ti ":${port}" -sTCP:LISTEN 2>/dev/null | head -1
        fi
    }

    kill_svc() {
        local pidfile="$1" icon="$2" label="$3" port="$4"
        local killed=false
        if [ -f "$pidfile" ]; then
            local pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                pkill -P "$pid" 2>/dev/null || true
                kill "$pid" 2>/dev/null || true
                sleep 0.5
                kill -9 "$pid" 2>/dev/null || true
                fmt "$icon" "$label" "stopped (PID $pid)"
                killed=true
            fi
            rm -f "$pidfile"
        fi
        if [ -n "$port" ]; then
            local orphan=$(pid_on_port "$port")
            if [ -n "$orphan" ]; then
                kill "$orphan" 2>/dev/null || true
                sleep 0.5
                kill -9 "$orphan" 2>/dev/null || true
                fmt "$icon" "$label" "stopped (orphan PID $orphan)"
                killed=true
            fi
        fi
        if [ "$killed" = false ]; then
            fmt "$icon" "$label" "was not running"
        fi
    }

    stop_postgres() {
        if docker compose ps --status running 2>/dev/null | grep -q postgres; then
            docker compose down > /dev/null 2>&1
            fmt "🐘" "PostgreSQL" "stopped"
        else
            fmt "🐘" "PostgreSQL" "was not running"
        fi
    }

    case "{{svc}}" in
        all)
            kill_svc "{{pid_dir}}/app.pid" "🌐" "Chainlit" "{{app_port}}"
            kill_svc "{{pid_dir}}/mcp.pid" "⚡" "FastMCP" "{{mcp_port}}"
            stop_postgres
            ;;
        postgres) stop_postgres ;;
        fastmcp)  kill_svc "{{pid_dir}}/mcp.pid" "⚡" "FastMCP" "{{mcp_port}}" ;;
        chainlit) kill_svc "{{pid_dir}}/app.pid" "🌐" "Chainlit" "{{app_port}}" ;;
        *)        echo "Unknown service: {{svc}}. Use: postgres, fastmcp, chainlit" && exit 1 ;;
    esac

# Restart services (all, or one: just restart fastmcp|chainlit|postgres)
restart svc="all":
    just stop {{svc}}
    just start {{svc}}

# Nuke DB volume (erases all data, run 'just start' after)
reset:
    #!/usr/bin/env bash
    set -uo pipefail
    echo ""
    echo "⚠️  WARNING: This will erase ALL database data (conversations, users, everything)."
    echo ""
    read -p "Type 'yes' to confirm: " confirm
    if [ "$confirm" = "yes" ]; then
        just stop
        echo "🗑️  Destroying PostgreSQL volume..."
        docker compose down -v > /dev/null 2>&1
        echo ""
        echo "✅ Database wiped. Run 'just start' when ready."
    else
        echo "Cancelled."
    fi

# Show service status
status:
    #!/usr/bin/env bash
    fmt() { printf "%s %-12s %s\n" "$1" "$2" "$3"; }
    if docker compose ps --status running 2>/dev/null | grep -q postgres; then
        fmt "🐘" "PostgreSQL" "✅ running"
    else
        fmt "🐘" "PostgreSQL" "❌ stopped"
    fi
    for svc in mcp:⚡:FastMCP app:🌐:Chainlit; do
        IFS=: read -r name icon label <<< "$svc"
        pidfile="{{pid_dir}}/${name}.pid"
        if [ -f "$pidfile" ] && kill -0 $(cat "$pidfile") 2>/dev/null; then
            fmt "$icon" "$label" "✅ running (PID $(cat "$pidfile"))"
        else
            fmt "$icon" "$label" "❌ stopped"
            rm -f "$pidfile" 2>/dev/null
        fi
    done

# Tail recent logs
logs:
    #!/usr/bin/env bash
    echo "=== FastMCP ===" && tail -20 {{log_dir}}/mcp.log 2>/dev/null || echo "(no log)"
    echo ""
    echo "=== Chainlit ===" && tail -20 {{log_dir}}/app.log 2>/dev/null || echo "(no log)"
    echo ""
    echo "=== PostgreSQL ===" && docker compose logs --tail 20 postgres 2>/dev/null || echo "(not running)"
