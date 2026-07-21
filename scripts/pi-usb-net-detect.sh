#!/bin/bash
# detect_pi.sh - Detect a Raspberry Pi connected via USB gadget mode

IFACE=""

# Find the USB gadget network interface (usually usb0, eth1, or enx...)
for iface in $(ip -o link show | awk -F': ' '{print $2}'); do
  if [[ "$iface" == usb* ]] || ip link show "$iface" | grep -q "usb"; then
    IFACE="$iface"
    break
  fi
done

# Fallback: look for enx* interfaces (common for USB ethernet gadgets)
if [[ -z "$IFACE" ]]; then
  IFACE=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^enx|^usb' | head -1)
fi

if [[ -z "$IFACE" ]]; then
  echo "No USB gadget network interface found. Is the Pi connected and gadget mode enabled?"
  exit 1
fi

echo "Found interface: $IFACE"

# Get the subnet from the host side of the interface
HOST_IP=$(ip -o -4 addr show "$IFACE" | awk '{print $4}' | cut -d'/' -f1)

if [[ -z "$HOST_IP" ]]; then
  echo "Interface $IFACE has no IP assigned yet. Try waiting a moment and rerunning."
  exit 1
fi

echo "Host IP on interface: $HOST_IP"
echo "Scanning for Pi..."

# The Pi typically gets .2 if host is .1, or vice versa (link-local /30 subnet)
SUBNET=$(echo "$HOST_IP" | cut -d'.' -f1-3)

for i in 1 2 3 4; do
  TARGET="$SUBNET.$i"
  if [[ "$TARGET" != "$HOST_IP" ]]; then
    if ping -c 1 -W 1 "$TARGET" &>/dev/null; then
      echo "Pi found at: $TARGET"
      echo "Connect with: ssh pi@$TARGET"
      exit 0
    fi
  fi
done

echo "Pi not found on $SUBNET.0/30. It may still be booting — try again in a few seconds."
exit 1