import typer

app = typer.Typer(help="A sample CLI.")


@app.command()
def hello(name: str):
    """Say hello to someone."""
    print(f"Hello {name}")


@app.command()
def goodbye(name: str, formal: bool = False):
    """Say goodbye to someone."""
    if formal:
        print(f"Goodbye, {name}. It was a pleasure.")
    else:
        print(f"Bye {name}!")


if __name__ == "__main__":
    app()
