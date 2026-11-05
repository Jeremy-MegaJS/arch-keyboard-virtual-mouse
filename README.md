# Virtual Mouse with Arrow Keys — Arch Linux

A keyboard-driven pointer-control utility for Arch Linux. It lets users move the cursor, click, drag, and scroll with the keyboard when no external mouse is connected. When a USB or Bluetooth mouse is detected, the arrow keys return to their normal behavior.

Developed and tested on Arch Linux with KDE Plasma.

## Key Features

- Accelerated cursor movement using the arrow keys.
- Vertical and horizontal scrolling with a modifier-key gesture.
- Middle-click, left-click, right-click, and drag interactions through configurable key gestures.
- Automatic detection of physical USB and Bluetooth mice.
- Normal keyboard behavior is restored while an external mouse is connected.
- User-level `systemd` service for background operation.

## Technology

- **Python** — input processing and pointer-control logic.
- **python-evdev** — reading Linux input events.
- **uinput** — creating virtual input devices.
- **keyd** — providing the virtual keyboard input source.
- **systemd (user services)** — service lifecycle management.
- **udev** — device rules and permissions.
- **Bash** — installation and maintenance commands.

## Requirements

- Arch Linux with an active `systemd` user session.
- `keyd`, `python`, `python-evdev`, and `systemd`.
- Access to the `keyd` virtual keyboard and `/dev/uinput` through the `input` group.
- A graphical session compatible with Linux input events.

The project was tested with the package versions documented in the repository's original setup notes. Current Arch package versions should generally be used rather than pinning those historical versions.

## Installation

Run the following commands from the repository root. If you already use `keyd`, back up your current configuration before installing: the included configuration replaces `/etc/keyd/default.conf`.

```bash
sudo pacman -Syu keyd python python-evdev
sudo systemctl enable --now keyd.service
sudo modprobe uinput
printf 'uinput\n' | sudo tee /etc/modules-load.d/uinput.conf
sudo usermod -aG input "$USER"
sudo install -Dm644 config/keyd/default.conf /etc/keyd/default.conf
sudo install -Dm644 config/udev/99-arrow-mouse-input.rules /etc/udev/rules.d/99-arrow-mouse-input.rules
install -Dm755 scripts/arrow-mouse.py "$HOME/.local/bin/arrow-mouse.py"
install -Dm644 systemd/arrow-mouse.service "$HOME/.config/systemd/user/arrow-mouse.service"
sudo udevadm control --reload-rules
sudo keyd reload
```

Restart the computer so the group membership, udev rule, and `uinput` module are applied. Then enable the user service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now arrow-mouse.service
```

Do not run the script manually while the service is active: both processes would attempt to capture the same virtual keyboard. If you already maintain custom `keyd` rules, integrate the exclusion in `config/keyd/default.conf` instead of overwriting your configuration.

## Controls

| Context | Input | Action |
| --- | --- | --- |
| No external mouse | Arrow keys | Move cursor with acceleration |
| No external mouse | Right Shift + arrows | Vertical or horizontal scrolling |
| No external mouse | Double-tap Right Shift | Middle click |
| No external mouse, Caps Lock on | Right arrow | Right click |
| No external mouse, Caps Lock on | One or two left-arrow taps | Single or double left click |
| No external mouse, Caps Lock on | Three quick left-arrow taps | Hold or release left button for dragging |
| Left button held | Arrow keys | Move cursor while dragging |
| External mouse connected | Arrow keys and Right Shift | Normal keyboard behavior |

Caps Lock keeps its regular capitalization function. Its click gestures only apply when no external mouse is detected. Single and double left clicks wait up to 300 ms to distinguish them from the three-tap drag gesture.

## Verification and Troubleshooting

```bash
id -nG
ls -l /dev/uinput
python -c 'import evdev; print("python-evdev ready")'
systemctl --user status arrow-mouse.service
journalctl --user -u arrow-mouse.service -b --no-pager
```

The `input` group should appear in `id -nG`, and `/dev/uinput` must be accessible to that group. The service log reports when arrow keys are controlling the cursor. If the virtual keyboard is not detected, check `keyd.service`, `sudo keyd monitor`, and the permissions of the relevant `event*` device.

## How It Works

`keyd` exposes a virtual keyboard. The Python program grabs its input events with `EVIOCGRAB`, forwards ordinary keys through a second virtual keyboard, and generates pointer movement, clicks, and scrolling through `uinput`. It checks for physical USB and Bluetooth mice using `udevadm`.

The implementation's movement and acceleration parameters are configurable near the beginning of `scripts/arrow-mouse.py`.

## Security Note

Membership in the `input` group can grant access to keyboard input events. Add only trusted users to this group and review the included udev and keyd configuration before installation.

## References

- [Arch Linux — keyd package](https://archlinux.org/packages/extra/x86_64/keyd/)
- [Arch Linux — python-evdev package](https://archlinux.org/packages/extra/x86_64/python-evdev/)
- [keyd documentation](https://github.com/rvaiya/keyd/blob/master/docs/keyd.scdoc)
- [python-evdev documentation](https://python-evdev.readthedocs.io/)

## Author

Developed by **Jeremy** — [GitHub](https://github.com/Jeremy-MegaJS).
