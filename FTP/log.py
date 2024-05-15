from datetime import datetime

class Console:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    PURPLE = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    @staticmethod
    def log( message, level="info"):
        colors = {
            "info": Console.RESET,
            "warning": Console.YELLOW,
            "error": Console.BLUE,
            "success": Console.GREEN,
            "critical":Console.RED
        }
        color = colors.get(level.lower(), Console.RESET)
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{time}]{color}{" " + message}{Console.RESET}")
