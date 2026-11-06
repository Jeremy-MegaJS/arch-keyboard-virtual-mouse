# Virtual Mouse with Arrow Keys — Arch Linux

**Bilingual project documentation / Documentación bilingüe**

A keyboard-driven pointer-control utility for Arch Linux. It lets users move the cursor, click, drag, and scroll with the keyboard when no external mouse is connected. When a USB or Bluetooth mouse is detected, the arrow keys return to their normal behavior.

Utilidad de control del puntero mediante el teclado para Arch Linux. Permite mover el cursor, hacer clic, arrastrar y desplazarse cuando no hay un mouse externo conectado. Cuando detecta un mouse USB o Bluetooth, las flechas recuperan su comportamiento habitual.

## Features / Funcionalidades

- Accelerated cursor movement using the arrow keys.
- Vertical and horizontal scrolling with a modifier-key gesture.
- Middle-click, left-click, right-click, and drag through configurable key gestures.
- Automatic detection of physical USB and Bluetooth mice.
- Normal keyboard behavior is restored while an external mouse is connected.
- User-level systemd service for background operation.

- Movimiento acelerado del cursor mediante las flechas.
- Desplazamiento vertical y horizontal mediante una combinación de teclas.
- Clic central, izquierdo, derecho y arrastre mediante gestos configurables.
- Detección automática de mouse físicos USB y Bluetooth.
- El teclado recupera su comportamiento normal cuando se conecta un mouse externo.
- Servicio systemd de usuario para ejecutarse en segundo plano.

## Technology / Tecnologías

- Python and python-evdev
- Linux uinput
- keyd
- systemd user services
- udev
- Bash

## Requirements / Requisitos

- Arch Linux with an active systemd user session.
- \`keyd\`, \`python\`, \`python-evdev\`, and systemd.
- Access to the \`keyd\` virtual keyboard and \`/dev/uinput\` through the \`input\` group.
- A graphical session compatible with Linux input events.

- Arch Linux con una sesión de usuario systemd activa.
- \`keyd\`, \`python\`, \`python-evdev\` y systemd.
- Acceso al teclado virtual de \`keyd\` y a \`/dev/uinput\` mediante el grupo \`input\`.
- Una sesión gráfica compatible con eventos de entrada de Linux.

## Installation / Instalación

Run these commands from the repository root. If you already use keyd, back up your configuration first: the included configuration replaces \`/etc/keyd/default.conf\`.

Ejecuta estos comandos desde la raíz del repositorio. Si ya utilizas keyd, respalda primero tu configuración: el archivo incluido reemplaza \`/etc/keyd/default.conf\`.

~~~bash
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
~~~

Restart the computer so group membership, udev rules, and the uinput module are applied. Then enable the user service:

Reinicia el equipo para aplicar la pertenencia al grupo, las reglas udev y el módulo uinput. Después, activa el servicio de usuario:

~~~bash
systemctl --user daemon-reload
systemctl --user enable --now arrow-mouse.service
~~~

Do not run the script manually while the service is active; both processes would try to capture the same virtual keyboard.

No ejecutes el script manualmente mientras el servicio esté activo; ambos procesos intentarían capturar el mismo teclado virtual.

## Controls / Controles

| Context / Contexto | Input / Entrada | Action / Acción |
| --- | --- | --- |
| No external mouse / Sin mouse externo | Arrow keys / Flechas | Move cursor / Mover cursor |
| No external mouse / Sin mouse externo | Right Shift + arrows / Mayús derecha + flechas | Scroll / Desplazarse |
| No external mouse / Sin mouse externo | Double-tap Right Shift / Doble toque en Mayús derecha | Middle click / Clic central |
| No external mouse / Sin mouse externo | Caps Lock on + Right arrow / Bloq Mayús + flecha derecha | Right click / Clic derecho |
| No external mouse / Sin mouse externo | Caps Lock on + left-arrow taps / Bloq Mayús + toques de flecha izquierda | Single/double click or drag / Clic simple, doble o arrastre |
| External mouse connected / Mouse externo conectado | Arrow keys / Flechas | Normal keyboard behavior / Comportamiento normal del teclado |

Caps Lock keeps its regular capitalization function. Its click gestures only apply when no external mouse is detected. Single and double left clicks wait up to 300 ms to distinguish them from the drag gesture.

Bloq Mayús conserva su función habitual de capitalización. Sus gestos de clic solo se activan cuando no se detecta un mouse externo. Los clics simples y dobles esperan hasta 300 ms para distinguirlos del gesto de arrastre.

## Verification / Verificación

~~~bash
id -nG
ls -l /dev/uinput
python -c 'import evdev; print("python-evdev ready")'
systemctl --user status arrow-mouse.service
journalctl --user -u arrow-mouse.service -b --no-pager
~~~

The \`input\` group should appear in \`id -nG\`, and \`/dev/uinput\` must be accessible to that group. If the virtual keyboard is not detected, check \`keyd.service\`, \`sudo keyd monitor\`, and the permissions of the relevant \`event*\` device.

El grupo \`input\` debe aparecer en \`id -nG\`, y \`/dev/uinput\` debe ser accesible para ese grupo. Si no se detecta el teclado virtual, revisa \`keyd.service\`, \`sudo keyd monitor\` y los permisos del dispositivo \`event*\` correspondiente.

## How it works / Cómo funciona

\`keyd\` exposes a virtual keyboard. The Python program captures its input events, forwards ordinary keys through a second virtual keyboard, and generates pointer movement, clicks, and scrolling through \`uinput\`. It checks for physical USB and Bluetooth mice through udev.

\`keyd\` expone un teclado virtual. El programa en Python captura sus eventos de entrada, reenvía las teclas normales mediante un segundo teclado virtual y genera movimiento del puntero, clics y desplazamiento mediante \`uinput\`. También comprueba la presencia de mouse físicos USB y Bluetooth mediante udev.

## Security note / Nota de seguridad

Membership in the \`input\` group can grant access to keyboard input events. Add only trusted users to this group and review the included udev and keyd configuration before installation.

La pertenencia al grupo \`input\` puede conceder acceso a eventos de entrada del teclado. Añade únicamente usuarios de confianza a ese grupo y revisa la configuración udev y keyd incluida antes de instalar.

## References / Referencias

- [Arch Linux — keyd](https://archlinux.org/packages/extra/x86_64/keyd/)
- [Arch Linux — python-evdev](https://archlinux.org/packages/extra/x86_64/python-evdev/)
- [keyd documentation](https://github.com/rvaiya/keyd/blob/master/docs/keyd.scdoc)
- [python-evdev documentation](https://python-evdev.readthedocs.io/)

## Author / Autor

Jeremy Torres — [GitHub](https://github.com/Jeremy-MegaJS)
