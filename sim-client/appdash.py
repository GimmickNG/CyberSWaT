import datetime as dt
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas as pd
import numpy as np

history_size = 600
LOSS_BINS = np.linspace(0, 1, 100)
RTT_BINS = np.linspace(0, 1, 100)
LOOKAHEAD_BINS = np.logspace(1, 4, 50, base=2)

rtt_file = open("rtt.csv", "r")
loss_file = open("losses.csv", "r")
lookaheads_file = open("../rest-service/lookaheads.csv", "r")

# skip headers
loss_file.readline()
rtt_file.readline()
lookaheads_file.readline()

fig, axes = plt.subplots(2, 3)
loss_ax, rtt_ax, lookaheads_ax = axes[0]
loss_hist_ax, rtt_hist_ax, lookaheads_hist_ax = axes[1]

loss_ax.set_title('Loss')
loss_ax.set_ylabel('Loss')
loss_ax.set_xlabel('Time')
loss_ax.set_xlim([0, history_size])
loss_ax.set_ylim([1e-4, 1])
loss_ax.set_yscale('log')

lookaheads_ax.set_title('Lookaheads')
lookaheads_ax.set_ylabel('Lookahead')
lookaheads_ax.set_xlabel('Time')
lookaheads_ax.set_xlim([0, history_size])
lookaheads_ax.set_ylim([1, 16])
lookaheads_ax.set_yscale('log', base=2)

rtt_ax.set_title('RTT')
rtt_ax.set_ylabel('RTT')
rtt_ax.set_xlabel('Time')
rtt_ax.set_xlim([0, history_size])
rtt_ax.set_ylim([0.08, 10])
rtt_ax.set_yscale('log')

rtt_df, losses_df, lookaheads_df = [1e-3]*history_size, [1e-3]*history_size, [1]*history_size

loss_hist = loss_hist_ax.hist(losses_df, LOSS_BINS, lw=1)[-1]
loss_hist_ax.set_ylim(top=50)
rtt_hist = rtt_hist_ax.hist(rtt_df, RTT_BINS, lw=1)[-1]
rtt_hist_ax.set_ylim(top=50)
lookaheads_hist = lookaheads_hist_ax.hist(lookaheads_df, LOOKAHEAD_BINS, lw=1)[-1]
lookaheads_hist_ax.set_ylim(top=50)
lookaheads_hist_ax.set_xscale('log', base=2)
lookaheads_hist_ax.set_xticks([1, 2, 4, 8, 16])

loss_hist_ax.set_ylabel('Frequency')
rtt_hist_ax.set_ylabel('Frequency')
lookaheads_hist_ax.set_ylabel('Frequency')

def bytes_remaining(f):
    currentPos=f.tell()
    f.seek(0, 2)
    length = f.tell()
    f.seek(currentPos)
    return length - currentPos

def draw_line_for(file, array, line, history):
    if bytes_remaining(file):
        df = pd.read_csv(file, header=None, index_col=0).to_numpy(float).flatten()[-history:].tolist()
        total_len = len(array) + len(df)
        if total_len < history:
            array.extend([df[0]] * (history - total_len))
            array.extend(df)
        array.extend(df)
        array[:] = array[-history:]
        line.set_ydata(array)

def draw_hist(data, container, bins):
    n, _ = np.histogram(data, bins)
    for count, rect in zip(n, container.patches):
        rect.set_height(count)
    return container.patches
    
def animate(i, loss_df, rtt_df, lookaheads_df, loss_line, rtt_line, lookaheads_line, loss_file, rtt_file, lookaheads_file, history):
    draw_line_for(loss_file, loss_df, loss_line, history)
    draw_line_for(rtt_file, rtt_df, rtt_line, history)
    draw_line_for(lookaheads_file, lookaheads_df, lookaheads_line, history)
    loss_hist_patches = draw_hist(loss_df, loss_hist, LOSS_BINS)
    rtt_hist_patches = draw_hist(rtt_df, rtt_hist, RTT_BINS)
    lookaheads_hist_patches = draw_hist(lookaheads_df, lookaheads_hist, LOOKAHEAD_BINS)
    return loss_line, rtt_line, lookaheads_line, *loss_hist_patches, *rtt_hist_patches, *lookaheads_hist_patches

# Set up plot to call animate() function periodically
duration = list(range(0, history_size))
loss_line, = loss_ax.plot(duration, [1e-3]*history_size)
rtt_line, = rtt_ax.plot(duration, [1e-3]*history_size)
lookaheads_line, = lookaheads_ax.plot(duration, [0]*history_size)
ani = animation.FuncAnimation(
    fig, animate, interval=1000, blit=True, fargs=(
        losses_df, rtt_df, lookaheads_df, 
        loss_line, rtt_line, lookaheads_line,
        loss_file, rtt_file, lookaheads_file,
        history_size
    )
)
plt.show()
