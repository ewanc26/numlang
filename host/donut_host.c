/*
 * donut_host — a tiny bespoke SDL2 engine for esolang demo programs.
 *
 * The language program computes a spinning torus and writes a token
 * protocol to stdout (whitespace-separated, so newline-terminated
 * numeric prints slot straight in):
 *
 *   F                          begin frame
 *   P x1 y1 x2 y2 x3 y3 x4 y4 r g b   shaded quad (window coords, floats fine)
 *   S                          swap/present
 *
 * After the producer's stream ends, the host replays the recorded frames
 * forever, so finite (unrolled) demos still animate. Headless:
 * --frames N exits after N presented frames (SDL_VIDEODRIVER=dummy works).
 *
 * Build: cc -std=c99 $(sdl2-config --cflags --libs) -o donut_host donut_host.c
 */
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    float coords[8];
    int r, g, b;
} Quad;

typedef struct {
    Quad *quads;
    int count, cap;
} Frame;

static Frame *frames = NULL;
static int nframes = 0, frame_cap = 0;

int main(int argc, char **argv) {
    int present_limit = -1;
    int width = 240, height = 240;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) present_limit = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--size") && i + 2 < argc) { width = atoi(argv[++i]); height = atoi(argv[++i]); }
    }

    /* Token-stream protocol: F / P <8 coords> <3 colours> / S. */
    Frame cur = {0};
    char tok[32];
    long total_quads = 0;
    while (scanf("%31s", tok) == 1) {
        if (tok[0] == 'F' && tok[1] == '\0') {
            cur.count = 0;
        } else if (tok[0] == 'S' && tok[1] == '\0') {
            if (nframes == frame_cap) {
                frame_cap = frame_cap ? frame_cap * 2 : 64;
                frames = realloc(frames, (size_t)frame_cap * sizeof(Frame));
                if (!frames) { fprintf(stderr, "donut_host: out of memory\n"); return 1; }
            }
            frames[nframes].count = cur.count;
            frames[nframes].cap = cur.count;
            frames[nframes].quads = cur.quads;
            total_quads += cur.count;
            nframes++;
            cur.quads = NULL;
            cur.count = 0;
            cur.cap = 0;
        } else if (tok[0] == 'P' && tok[1] == '\0') {
            float v[11];
            int ok = 1;
            for (int i = 0; i < 11; i++) {
                if (scanf("%f", &v[i]) != 1) { ok = 0; break; }
            }
            if (!ok) { fprintf(stderr, "donut_host: bad P line\n"); return 2; }
            if (cur.count == cur.cap) {
                cur.cap = cur.cap ? cur.cap * 2 : 64;
                cur.quads = realloc(cur.quads, (size_t)cur.cap * sizeof(Quad));
                if (!cur.quads) { fprintf(stderr, "donut_host: out of memory\n"); return 1; }
            }
            Quad *q = &cur.quads[cur.count++];
            for (int i = 0; i < 8; i++) q->coords[i] = v[i];
            q->r = v[8] < 0 ? 0 : (v[8] > 255 ? 255 : (int)v[8]);
            q->g = v[9] < 0 ? 0 : (v[9] > 255 ? 255 : (int)v[9]);
            q->b = v[10] < 0 ? 0 : (v[10] > 255 ? 255 : (int)v[10]);
        }
    }
    if (nframes == 0) { fprintf(stderr, "donut_host: no frames in input\n"); return 2; }
    fprintf(stderr, "donut_host: %d frames, %ld quads\n", nframes, total_quads);

    if (SDL_Init(SDL_INIT_VIDEO) != 0) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Window *win = SDL_CreateWindow("esolang torus", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                       width, height, SDL_WINDOW_SHOWN);
    if (!win) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!ren) ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
    if (!ren) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }

    int presented = 0;
    int running = 1;
    while (running) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) running = 0;
            if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_ESCAPE) running = 0;
        }
        Frame *f = &frames[presented % nframes];
        SDL_SetRenderDrawColor(ren, 12, 10, 20, 255);
        SDL_RenderClear(ren);
        for (int i = 0; i < f->count; i++) {
            Quad *q = &f->quads[i];
            SDL_Vertex verts[6];
            static const int tri[6] = {0, 1, 2, 0, 2, 3};
            for (int k = 0; k < 6; k++) {
                int idx = tri[k] * 2;
                verts[k].position.x = q->coords[idx];
                verts[k].position.y = q->coords[idx + 1];
                verts[k].color.r = (Uint8)q->r;
                verts[k].color.g = (Uint8)q->g;
                verts[k].color.b = (Uint8)q->b;
                verts[k].color.a = 255;
            }
            SDL_RenderGeometry(ren, NULL, verts, 6, NULL, 0);
        }
        SDL_RenderPresent(ren);
        presented++;
        if (present_limit >= 0 && presented >= present_limit) running = 0;
        if (present_limit < 0) SDL_Delay(16);
    }

    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
