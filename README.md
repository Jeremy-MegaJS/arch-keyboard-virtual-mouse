# Mouse virtual con flechas en Arch Linux

Configuración para controlar el cursor con el teclado cuando no hay un mouse externo. Es la configuración que uso en Arch Linux con `keyd`, `python-evdev`, `uinput` y un servicio de `systemd --user`. El script detecta si se conecta un mouse USB o Bluetooth y devuelve las flechas a su función normal.

## Controles

| Situación | Teclas | Acción |
| --- | --- | --- |
| Sin mouse externo | Flechas | Mover el cursor con aceleración |
| Sin mouse externo | Shift derecho + flechas | Desplazamiento vertical u horizontal |
| Sin mouse externo | Dos toques rápidos de Shift derecho | Clic central |
| Sin mouse externo, Caps Lock activado | Flecha derecha | Clic derecho |
| Sin mouse externo, Caps Lock activado | Flecha izquierda, uno o dos toques | Uno o dos clics izquierdos |
| Sin mouse externo, Caps Lock activado | Tres toques rápidos de flecha izquierda | Activar o soltar el botón izquierdo sostenido para arrastrar |
| Con botón izquierdo sostenido | Flechas | Mover el cursor y arrastrar; la izquierda responde al pulsarla |
| Con mouse externo | Flechas y Shift derecho | Comportamiento normal del teclado |

Caps Lock mantiene su función habitual de mayúsculas. Sus combinaciones de clic solo tienen efecto cuando no se detecta un mouse externo. Los clics izquierdos de uno o dos toques se esperan hasta 300 ms para distinguirlos del gesto de tres toques. El movimiento a la izquierda mientras el botón está sostenido comienza de inmediato. Los toques para soltar el botón pueden producir un pequeño desplazamiento, porque comparten la misma tecla con el movimiento.

## Requisitos

- Arch Linux con `systemd` y una sesión de usuario activa.
- Paquetes oficiales `keyd`, `python`, `python-evdev` y `systemd`.
- Acceso del usuario al teclado virtual de `keyd` y a `/dev/uinput` mediante el grupo `input`.
- Una sesión gráfica compatible con eventos de entrada Linux. Se usa en KDE Plasma; el procesamiento de teclas ocurre en `evdev`/`uinput`, no en atajos de KDE.

Las versiones comprobadas en el equipo original el 25 de octubre de 2026 fueron `keyd 2.6.0-5`, `python-evdev 2.0.0-1`, Python `3.14.8-1` y `systemd 262.1-1`. No es necesario fijarlas: instala las versiones actuales de Arch.

## Instalación

Ejecuta estos comandos desde la raíz de este repositorio. Antes de copiar `default.conf`, guarda tu configuración actual de `keyd` si ya tienes una: este archivo la sustituye.

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

**Reinicia el equipo** para aplicar la pertenencia al grupo `input`, la regla de `udev` y la carga de `uinput`. Después, habilita el servicio desde tu sesión de usuario:

```bash
systemctl --user daemon-reload
systemctl --user enable --now arrow-mouse.service
```

No ejecutes el script a la vez que el servicio: ambos intentarían capturar el mismo teclado virtual. La línea `-cafe:feed` en `config/keyd/default.conf` excluye el teclado proxy creado por el script para evitar que `keyd` lo procese de nuevo. Si ya tienes reglas propias de `keyd`, integra esa exclusión en vez de sobrescribirlas.

## Verificación

```bash
id -nG
ls -l /dev/uinput
python -c 'import evdev; print("python-evdev listo")'
systemctl --user status arrow-mouse.service
journalctl --user -u arrow-mouse.service -b --no-pager
```

`id -nG` debe incluir `input`; `/dev/uinput` debe ser accesible al grupo. El registro indica `Sin mouse: flechas controlan el cursor` cuando se activa el modo virtual. Si no se encuentra el teclado de `keyd`, revisa `systemctl status keyd.service`, `sudo keyd monitor` y los permisos del dispositivo `event*` correspondiente. El script busca literalmente un dispositivo llamado `keyd virtual keyboard` que emita `KEY_UP`; si tu versión de `keyd` usa otro nombre, ajusta `find_keyd_keyboard()`.

Para aplicar una actualización del script después de instalarlo:

```bash
install -Dm755 scripts/arrow-mouse.py "$HOME/.local/bin/arrow-mouse.py"
systemctl --user restart arrow-mouse.service
```

Para detenerlo temporalmente: `systemctl --user stop arrow-mouse.service`. Para deshabilitarlo: `systemctl --user disable --now arrow-mouse.service`.

## Cómo funciona

`keyd` presenta un teclado virtual. El script toma sus eventos con `EVIOCGRAB`, reenvía las teclas normales por un segundo teclado virtual y genera movimiento, clics y desplazamiento con `uinput`. Detecta dispositivos físicos USB o Bluetooth mediante `udevadm` cada 0,6 segundos. La velocidad del cursor aumenta hasta 1600 unidades/s, con aceleración de 4500 unidades/s² y un bucle objetivo de 120 Hz. Los valores se ajustan al inicio de `scripts/arrow-mouse.py`.

El grupo `input` permite leer dispositivos de entrada, incluidas pulsaciones de teclas; concede ese acceso solo a usuarios de confianza. La regla de `udev` de este repositorio limita el cambio de permisos al teclado virtual de `keyd`. En Arch, la regla del paquete para `/dev/uinput` usa el grupo `input` y modo `0660`.

## Fuentes

- [Paquete `keyd` de Arch Linux](https://archlinux.org/packages/extra/x86_64/keyd/)
- [Paquete `python-evdev` de Arch Linux](https://archlinux.org/packages/extra/x86_64/python-evdev/)
- [Manual de configuración de `keyd`](https://github.com/rvaiya/keyd/blob/master/docs/keyd.scdoc)
- [Documentación de `python-evdev`](https://python-evdev.readthedocs.io/)
