from dash import Dash, html, dcc, Output, Input
import plotly.express as px
import pandas as pd
import glob

inline = {'display': 'inline'}
app = Dash(__name__)
app.layout = html.Div(children=[
    html.Span(
        className="row",
        children=[
            html.Label("Losses file:"),
            dcc.Dropdown(options=glob.glob("*.csv"), value='losses.csv', id='loss-file'),
            html.Label("RTT file:"),
            dcc.Dropdown(options=glob.glob("*.csv"), value='rtt.csv', id='rtt-file'),
        ]
    ),
    html.Div(
        className="row",
        children=[
            html.Div(
                className="six columns",
                children=[
                    html.Div(
                        children=dcc.Graph(id='loss_graph'),
                    )
                ]
            ),
            html.Div(
                className="six columns",
                children=html.Div(
                    children=dcc.Graph(id='rtt_graph'),
                )
            )
        ]
    ),
    dcc.Interval(
        id='interval-component',
        interval=5000,
        n_intervals=0
    )
])

@app.callback(
    Output(component_id='loss_graph', component_property='figure'),
    Output(component_id='rtt_graph', component_property='figure'),
    Input('interval-component', 'n_intervals'),
    Input('loss-file', 'value'),
    Input('rtt-file', 'value')
)

def update_graph(n_intervals, loss, rtt):
    losses_df = pd.read_csv(loss)
    rtt_df = pd.read_csv(rtt)

    losses = px.line(losses_df.iloc[-600:], x="Time (Relative)", y="Loss", title='Loss')
    rtt = px.line(rtt_df.iloc[-600:], x="Time (Relative)", y="RTT", title='RTT')
    return losses, rtt

if __name__ == '__main__':
    app.run_server(debug=False, dev_tools_hot_reload=False)