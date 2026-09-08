import typer

app = typer.Typer(
    name="hostme",
    help="Личный аналог surge.sh — деплой сайтов на свои VPS.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    pass


if __name__ == "__main__":
    app()
