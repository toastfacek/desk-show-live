# How the show is run

This is a plan, not an app. No code. Nothing here spends money.

This repo is for a fake live desk show: a cartoon host sits at a desk and talks about posts from a feed (like Twitter). We buy short talking clips from a video service, then play them in a row so it feels live. The host has to look like the same person from clip to clip, so each new clip starts on the last picture of the last clip.

This page is about the extra piece we need around those clips: a picker (the conductor) that decides what is on screen when a clip is late or we want a breath. It does not write the jokes. It only picks the picture and how long it stays.

The rest of this repo still has the older, longer notes. This page is the short version you can decide from.

## The whole thing

We have one talking picture. Making five seconds of it takes about five seconds.

If that talking picture is the only thing on screen, the show freezes the first time a clip is late.

So someone has to pick what you look at while the next clip is cooking. That someone is the conductor. It never writes jokes. It only picks the picture and how long it stays.

Three seconds of a frozen face looks broken. Three seconds on a tweet card, with music still going, looks like the show taking a breath.

## Who does what

The writer decides what is said.

The conductor decides what is seen, and when.

The video model only acts out a line it already has.

The person who pastes the tweet on screen just follows orders. They do not pick shots.

You can override anything, but only when a clip ends. A clip is one piece of picture and sound stuck together. You cannot cut it in half.

## What can be on screen

Almost everything is free.

The talking host clip costs money every time.

A still of the host sitting there, a tweet card, the desk picture, a freeze on the last frame, and the music: those are free or we make them once and reuse them.

So we have one camera that costs money, and a pile of pictures that do not.

Do not make eight talking cameras. That is eight bills.

## The rule that makes the math mean

The next talking clip has to start from the last frame of the last talking clip. That last frame does not exist until the last clip is fully done and we pull the picture off it.

So we cannot start the next clip the moment we press go on this one. We play this clip while the next one cooks. That is the only overlap we get.

If cooking takes longer than playing, we must show a free picture in the gap. That is not decoration. That is how the show stays on.

## Three things to lock

1. Only one talking video on screen. Ever. The other "cameras" are pictures.
2. Writer writes. Conductor shows. The conductor does not touch the words.
3. Practice with fake clips (no money) until the picking rules work. Then spend.

## Three things only you can pick

1. Does the host's voice come from the video, or from a cheaper voice tool? If the voice is separate, we can talk over a tweet card for free. The trade is the mouth may not match.
2. Is this a timed episode, or does it just keep going?
3. Are you watching when it runs? If yes, you can skip a bad clip. If no, the rules have to be more careful on their own.

## The surprise

A second host is almost free if they take turns.

You still only show one talking picture, so the bill per minute stays the same.

While A talks, B's next clip can cook. While B talks, A's next clip can cook. Each host gets extra time. The show stops almost dying, without costing more.

That is a stronger reason for a second host than "they can banter."

## What we do not do yet

No live stream.
No wall of screens for you to click.
No second talking window at the same time.
No generating extra angles just to have angles.

First job is still the same: sixty seconds of one host that does not stall. The conductor starts as a tiny picker that, on day one, just shows the host full screen and only switches when the next clip is not ready.

## Two cheap tests worth a couple dollars

Try 8-second and 10-second clips once (about $1.20). Longer clips might give us more slack for the same money.

Try the new "pin this face" video call once (about $2). If a pinned still is enough, we may not need the last-frame chain at all, and a lot of this page gets simpler.
