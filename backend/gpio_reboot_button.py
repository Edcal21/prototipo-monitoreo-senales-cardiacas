import os
from signal import pause

from gpiozero import Button


GPIO_REBOOT_BUTTON = int(os.getenv("ECG_REBOOT_BUTTON_GPIO", "5"))
HOLD_TIME_S = float(os.getenv("ECG_REBOOT_HOLD_TIME_S", "2"))


def reboot_system():
    print("Boton presionado por 2 segundos. Reiniciando el sistema...")
    os.system("sudo /sbin/reboot")


button = Button(GPIO_REBOOT_BUTTON, pull_up=True, bounce_time=0.1, hold_time=HOLD_TIME_S)
button.when_held = reboot_system

print(f"Boton de reinicio activo en GPIO{GPIO_REBOOT_BUTTON}. Mantener {HOLD_TIME_S}s.")
pause()
