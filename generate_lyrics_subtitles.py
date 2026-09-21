"""
Generates high-precision ASS subtitles for Michael Jackson - They Don't Care About Us
Styles conform strictly to the Song / Lyric Video specifications:
- Clean minimal intro on black screen (0.0s - 2.0s)
- Modern bold sans-serif (Segoe UI Bold / Arial Bold)
- Beautifully positioned in lower safe area (MarginV=260) so it never covers the artist
- Crisp white text with single consistent warm gold accent (&H0000CCFF&)
- Smooth alpha fades (120ms), no bouncing, no emojis
"""

import os

def create_ass_subtitles(output_path: str):
    header = """[Script Info]
Title: Michael Jackson - They Don't Care About Us (Vertical Short)
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: IntroArtist,Segoe UI,46,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,8,0,1,0,0,2,60,60,1000,1
Style: IntroTrack,Segoe UI,32,&H0000CCFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,10,0,1,0,0,2,60,60,930,1
Style: LyricMain,Segoe UI,50,&H00FFFFFF,&H000000FF,&H00121212,&H80000000,1,0,0,0,100,100,1,0,1,2.0,3.0,2,80,80,260,1
Style: LyricPunch,Segoe UI,54,&H00FFFFFF,&H000000FF,&H00121212,&H80000000,1,0,0,0,100,100,2,0,1,2.5,3.5,2,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = [
        # Intro card on clean black screen (0.2s to 1.8s)
        'Dialogue: 2,0:00:00.20,0:00:01.80,IntroArtist,,0,0,0,,{\\fad(200,200)}MICHAEL JACKSON',
        'Dialogue: 2,0:00:00.20,0:00:01.80,IntroTrack,,0,0,0,,{\\fad(200,200)}THEY DON\'T CARE ABOUT US',

        # 0:02.80 - 0:06.20: Chorus opening
        'Dialogue: 1,0:00:02.80,0:00:06.20,LyricMain,,0,0,0,,{\\fad(120,120)}All I wanna say is that they don\'t really {\\c&H0000CCFF&}care about us{\\c&H00FFFFFF&}',

        # 0:11.20 - 0:14.80: Bridge 2 start
        'Dialogue: 1,0:00:11.20,0:00:14.80,LyricMain,,0,0,0,,{\\fad(120,120)}Tell me what has become of {\\c&H0000CCFF&}my rights?{\\c&H00FFFFFF&}',

        # 0:15.20 - 0:18.40: Question
        'Dialogue: 1,0:00:15.20,0:00:18.40,LyricMain,,0,0,0,,{\\fad(120,120)}Am I {\\c&H0000CCFF&}invisible{\\c&H00FFFFFF&} because you ignore me?',

        # 0:19.10 - 0:21.60: Proclamation
        'Dialogue: 1,0:00:19.10,0:00:21.60,LyricMain,,0,0,0,,{\\fad(120,120)}Your proclamation promised me free {\\c&H0000CCFF&}liberty{\\c&H00FFFFFF&}, now',

        # 0:21.80 - 0:24.40: Victim of shame
        'Dialogue: 1,0:00:21.80,0:00:24.40,LyricMain,,0,0,0,,{\\fad(120,120)}I\'m tired of being the {\\c&H0000CCFF&}victim of shame{\\c&H00FFFFFF&}',

        # 0:24.60 - 0:28.20: Bad name
        'Dialogue: 1,0:00:24.60,0:00:28.20,LyricMain,,0,0,0,,{\\fad(120,120)}They\'re throwing me in a class with a {\\c&H0000CCFF&}bad name{\\c&H00FFFFFF&}',

        # 0:29.00 - 0:31.40: Land from which I came
        'Dialogue: 1,0:00:29.00,0:00:31.40,LyricMain,,0,0,0,,{\\fad(120,120)}I can\'t believe this is {\\c&H0000CCFF&}the land{\\c&H00FFFFFF&} from which I came',

        # 0:31.80 - 0:34.20: Hate to say it
        'Dialogue: 1,0:00:31.80,0:00:34.20,LyricMain,,0,0,0,,{\\fad(120,120)}You know I really do {\\c&H0000CCFF&}hate to say it{\\c&H00FFFFFF&}',

        # 0:34.50 - 0:37.00: Government don't wanna see
        'Dialogue: 1,0:00:34.50,0:00:37.00,LyricMain,,0,0,0,,{\\fad(120,120)}The {\\c&H0000CCFF&}government{\\c&H00FFFFFF&} don\'t wanna see',

        # 0:37.30 - 0:40.20: Climax: Roosevelt
        'Dialogue: 1,0:00:37.30,0:00:40.20,LyricPunch,,0,0,0,,{\\fad(100,100)}But if {\\c&H0000CCFF&}Roosevelt{\\c&H00FFFFFF&} were living',

        # 0:40.40 - 0:43.00: He wouldn't let this be
        'Dialogue: 1,0:00:40.40,0:00:43.00,LyricPunch,,0,0,0,,{\\fad(100,100)}He wouldn\'t {\\c&H0000CCFF&}let this be{\\c&H00FFFFFF&}, no, no',

        # 0:43.20 - 0:45.03: Outro chant
        'Dialogue: 1,0:00:43.20,0:00:45.03,LyricMain,,0,0,0,,{\\fad(100,120)}Skin head, dead head, {\\c&H0000CCFF&}everybody gone bad{\\c&H00FFFFFF&}'
    ]

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        for ev in events:
            f.write(ev + '\n')
    print(f"Subtitles updated: {output_path}")

if __name__ == "__main__":
    out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics.ass")
    create_ass_subtitles(out_file)
