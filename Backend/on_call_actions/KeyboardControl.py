import pyautogui


def digitar_texto(texto):
    pyautogui.write(texto, interval=0.3)