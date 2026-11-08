# Instructions

The purpose of this project is to build Alvex Editor, a video editing and production tool.

The use-case we're designing for is real estate video production, but the tool should be designed to enable more generalized video production.

The specific workflow for real estate is:

1. I fly my drone to record specific clips to satisfy the template.
2. Once the drone flight is complete, I download the clips to a folder and include an MP3 for the sound track.
3. The tool analyzes the sound track to map out the clip lengths and transition points, analyzes the clips to align with the template, then composes the video complete with intro, outro, titles, overlays, and sequenced clips.
4. I then review the resulting video and when it's ready, I'll upload it to YouTube.

A user can define a video template, provide clips, a sound track, overlays, branding, or other relevant media to build the video.

# AI Use

This tool will leverage AI models provided by Ollama. Only provide documentation for setting up Ollama and configuring the tool to integrate with it.

# Templates

Templates live in the `templates` folder and should be markdown files. They are human-friendly definitions that the tool will use as a target for producing the video.

# Sound Track

The sound track provides the rhythm and pacing of the video. When provided, the tool analyzes the track to identify the moments where a transition from one clip to the next is appropriate.

# Clips

Video clips should be standard clips that are about 8-12 seconds long. The Intro & Outro clips can be longer to allow for time to show text overlays and fade in/out.

