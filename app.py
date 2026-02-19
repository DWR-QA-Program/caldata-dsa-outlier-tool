from shiny import App, reactive, render, ui

app_ui = ui.page_fluid(
    ui.h2("PyShiny Infrastructure Test App"),
    ui.input_text("name", "Your name", value="Tester"),
    ui.input_action_button("ping", "Ping server"),
    ui.hr(),
    ui.output_text_verbatim("status"),
)


def server(input, output, session):
    @reactive.calc
    def clicks():
        return input.ping()

    @output
    @render.text
    def status():
        return (
            f"Hello, {input.name()}. "
            f"Button clicks: {clicks()}. "
            "If you can see this update, reactivity and server are working."
        )


app = App(app_ui, server)
