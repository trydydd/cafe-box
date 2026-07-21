#!/bin/bash
# pi-usb-net-setup.sh — Assign a static IP to the host side of the USB gadget interface.
#
# Usage: sudo ./scripts/pi-usb-net-setup.sh
#
# Assigns 192.168.7.1/24 to the detected USB gadget interface so that the Pi
# (configured at 192.168.7.2) is reachable over SSH.
#
# If the interface has a stable MAC (set via g_ether modprobe config), also
# creates a persistent NetworkManager connection so the IP is assigned
# automatically on future plug-ins without needing to re-run this script.

set -euo pipefail

HOST_IP="192.168.7.1"
PREFIX="24"
NM_CON_NAME="hearth-usb-host"

# Detect the USB gadget interface (enx*, usb*)
IFACE=""

for iface in $(ip -o link show | awk -F': ' '{print $2}'); do
  if [[ "$iface" == usb* ]] || ip link show "$iface" | grep -q "usb"; then
    IFACE="$iface"
    break
  fi
done

if [[ -z "$IFACE" ]]; then
  IFACE=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^enx|^usb' | head -1)
fi

if [[ -z "$IFACE" ]]; then
  echo "No USB gadget interface found. Is the Pi connected with a data cable and gadget mode enabled?"
  exit 1
fi

echo "Found interface: $IFACE"

# Check if already assigned
EXISTING=$(ip -o -4 addr show "$IFACE" 2>/dev/null | awk '{print $4}' | head -1)
if [[ "$EXISTING" == "$HOST_IP/$PREFIX" ]]; then
  echo "Interface already has $HOST_IP/$PREFIX — nothing to do."
else
  if [[ $EUID -ne 0 ]]; then
    echo "Root required to assign IP. Re-run with sudo."
    exit 1
  fi

  ip addr flush dev "$IFACE"
  ip addr add "$HOST_IP/$PREFIX" dev "$IFACE"
  ip link set "$IFACE" up

  SUBNET=$(echo "$HOST_IP" | cut -d'.' -f1-3)
  ip route replace "$SUBNET.0/$PREFIX" dev "$IFACE"

  echo "Assigned $HOST_IP/$PREFIX to $IFACE"
fi

# Create a persistent NM connection if one doesn't already exist for this interface.
# This only makes sense when the interface has a stable (non-random) MAC, i.e.
# after the Pi has booted with the g_ether modprobe MAC config in place.
if command -v nmcli &>/dev/null; then
  if nmcli -g GENERAL.CONNECTION device show "$IFACE" 2>/dev/null | grep -q "$NM_CON_NAME"; then
    echo "Persistent NM connection '$NM_CON_NAME' already active on $IFACE."
  elif nmcli connection show "$NM_CON_NAME" &>/dev/null; then
    echo "Persistent NM connection '$NM_CON_NAME' exists — bringing it up."
    nmcli connection up "$NM_CON_NAME" 2>/dev/null || true
  else
    echo "Creating persistent NM connection '$NM_CON_NAME' for $IFACE..."
    nmcli connection add \
      type ethernet \
      ifname "$IFACE" \
      con-name "$NM_CON_NAME" \
      ip4 "$HOST_IP/$PREFIX" \
      ipv4.never-default yes \
      autoconnect yes
    nmcli connection up "$NM_CON_NAME" 2>/dev/null || true
    echo "NM connection created. $IFACE will be auto-configured on future plug-ins."
  fi
fi

echo "Pi should be reachable at 192.168.7.2 once booted."
