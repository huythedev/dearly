#!/bin/sh
set -eu

fail() { printf 'Dearly frontend: %s\n' "$*" >&2; exit 1; }

address=${DEARLY_BACKEND_ADDRESS:-}
if [ -z "$address" ]; then
    printf 'Backend address (IP:port or http[s]://host:port): ' >&2
    IFS= read -r address || fail 'Set DEARLY_BACKEND_ADDRESS, or run with docker run -it to enter it.'
fi
case "$address" in
    http://*) scheme=http; authority=${address#http://} ;;
    https://*) scheme=https; authority=${address#https://} ;;
    *://*) fail 'Only http:// and https:// backend addresses are supported.' ;;
    *) scheme=http; authority=$address ;;
esac
authority=${authority%/}
case "$authority" in *[[:space:]]*) fail 'The backend address must not contain whitespace.' ;; esac
printf '%s\n' "$authority" | LC_ALL=C grep -Eq '^([A-Za-z0-9_]([A-Za-z0-9_.-]*[A-Za-z0-9_])?|\[[0-9A-Fa-f:.]+\]):[0-9]{1,5}$' \
    || fail 'Use a hostname or IP and an explicit port, without credentials, paths, or queries.'
backend_port=${authority##*:}
[ "$backend_port" -ge 1 ] && [ "$backend_port" -le 65535 ] || fail 'Backend port must be between 1 and 65535.'
host=${authority%:*}
DEARLY_BACKEND_HOST=${host#\[}; DEARLY_BACKEND_HOST=${DEARLY_BACKEND_HOST%\]}

# Nginx's async resolver does not read /etc/hosts. Respect host-gateway mappings
# (including host.docker.internal on Linux) while retaining DNS refresh for Compose services.
mapped=$(awk -v name="$DEARLY_BACKEND_HOST" '{ for (i=2;i<=NF;i++) if ($i==name) { print $1; exit } }' /etc/hosts)
if [ -n "$mapped" ]; then
    case "$mapped" in *:*) authority="[$mapped]:$backend_port" ;; *) authority="$mapped:$backend_port" ;; esac
fi
DEARLY_BACKEND_URL="$scheme://$authority"
DEARLY_FRONTEND_LISTEN_PORT=${DEARLY_FRONTEND_LISTEN_PORT:-8080}
printf '%s\n' "$DEARLY_FRONTEND_LISTEN_PORT" | LC_ALL=C grep -Eq '^[0-9]{1,5}$' || fail 'Frontend listen port must be numeric.'
[ "$DEARLY_FRONTEND_LISTEN_PORT" -ge 1 ] && [ "$DEARLY_FRONTEND_LISTEN_PORT" -le 65535 ] || fail 'Frontend listen port must be between 1 and 65535.'
DEARLY_DNS_RESOLVER=$(awk '$1=="nameserver" { print $2; exit }' /etc/resolv.conf)
case "$DEARLY_DNS_RESOLVER" in *:*) DEARLY_DNS_RESOLVER="[$DEARLY_DNS_RESOLVER]" ;; esac
printf '%s\n' "$DEARLY_DNS_RESOLVER" | LC_ALL=C grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$|^\[[0-9A-Fa-f:]+\]$' || fail 'No usable DNS resolver in /etc/resolv.conf.'
export DEARLY_BACKEND_URL DEARLY_BACKEND_HOST DEARLY_FRONTEND_LISTEN_PORT DEARLY_DNS_RESOLVER
template=${DEARLY_NGINX_TEMPLATE:-/etc/nginx/dearly.conf.template}
config=${DEARLY_NGINX_CONFIG:-/tmp/dearly-nginx.conf}
envsubst '${DEARLY_BACKEND_URL} ${DEARLY_BACKEND_HOST} ${DEARLY_FRONTEND_LISTEN_PORT} ${DEARLY_DNS_RESOLVER}' < "$template" > "$config"
printf 'Dearly frontend listening on %s; proxying API/chat to %s\n' "$DEARLY_FRONTEND_LISTEN_PORT" "$DEARLY_BACKEND_URL"
nginx -t -c "$config"
exec nginx -c "$config" -g 'daemon off;'
