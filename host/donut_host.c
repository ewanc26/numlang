/*
 * donut_host — SDL2 host for the phase-2 donut vertex-stream protocol.
 *
 * A faithful embed of the canonical renderer in doughnut.c (800x600 torus,
 * U_STEPS=50, V_STEPS=30, R_MAJOR=2.0, R_MINOR=0.8): the language program
 * streams per-frame *vertices* and this host owns the torus mesh, the
 * triangle indices, the z-buffered Gouraud rasterizer and the palette,
 * matching doughnut.c's generate_torus()/draw_triangle() exactly.
 *
 * Token stream (whitespace-separated, one value per line):
 *   F                      begin frame
 *   px py z intensity      one vertex (1500 per frame, i*30+j order)
 *   ...
 *   S                      present
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
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define WIDTH 800
#define HEIGHT 600

#define R_MAJOR 2.0f
#define R_MINOR 0.8f
#define U_STEPS 50
#define V_STEPS 30

typedef struct {
    float x, y, z;
} Vector3;

typedef struct {
    int i0, i1, i2;
} Triangle;

/* Streamed vertex: projected position, camera-space depth, light intensity. */
typedef struct {
    float x, y, z, intensity;
} Vertex;

/* Global buffers for mesh data (doughnut.c layout) */
static Vector3 base_vertices[U_STEPS * V_STEPS];
static Vector3 base_normals[U_STEPS * V_STEPS];
static Triangle triangles[U_STEPS * V_STEPS * 2];
static int total_triangles = 0;

static float zbuffer[WIDTH * HEIGHT];
static Uint32 framebuffer[WIDTH * HEIGHT];
/* ------------------------------------------------------------------ */
/* Canonical per-frame logging — byte-identical format shared by       */
/* doughnut_logged.c and every donut_host. JSON Lines, one object per  */
/* presented frame:                                                    */
/*  {"frame":N,"vertices":N,"stream_checksum":"<16hex>",               */
/*   "vertex_minmax":{"px":[min,max],"py":[..],"z":[..],"i":[..]},     */
/*   "first_vertex":[px,py,z,i],"last_vertex":[px,py,z,i],             */
/*   "z_writes":N,"wireframe_pixels":N,"fb_checksum":"<16hex>",         */
/*   "wall_ms":f}                                                      */
/* Rules: checksums are 64-bit FNV-1a (offset 14695981039346656037,    */
/* prime 1099511628211) printed as 16 lowercase hex chars;              */
/* stream_checksum hashes the raw text of the frame's 6000 vertex      */
/* values in stream order, no separators (here: the token bytes        */
/* exactly as read from stdin); fb_checksum hashes the 800x600x4      */
/* framebuffer bytes in memory; floats use round-trip-shortest %.9g;  */
/* wall_ms is %.3f and covers the render only (clear..raster, no      */
/* present).                                                          */
/* ------------------------------------------------------------------ */
static FILE *log_file = NULL;
static unsigned long long log_z_writes = 0;
static unsigned long long log_wireframe_pixels = 0;

static unsigned long long log_fnv_init(void) { return 14695981039346656037ULL; }
static unsigned long long log_fnv_text(unsigned long long h, const char *s) {
    while (*s) { h ^= (unsigned char)(*s++); h *= 1099511628211ULL; }
    return h;
}
static unsigned long long log_fnv_fb(unsigned long long h) {
    const unsigned char *b = (const unsigned char *)framebuffer;
    size_t n = sizeof(framebuffer);
    for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 1099511628211ULL; }
    return h;
}
static double log_wall_ms(Uint64 t0, Uint64 t1) {
    Uint64 freq = SDL_GetPerformanceFrequency();
    return freq ? (double)(t1 - t0) * 1000.0 / (double)freq : 0.0;
}
/* Emit one canonical frame record (see the format comment above).    */
static void log_frame(int frame, int nverts, const float *pxv, const float *pyv,
                      const float *zv, const float *iv,
                      unsigned long long stream_checksum, double wall_ms) {
    if (!log_file || nverts <= 0) return;
    float mn[4] = {pxv[0], pyv[0], zv[0], iv[0]};
    float mx[4] = {pxv[0], pyv[0], zv[0], iv[0]};
    for (int k = 1; k < nverts; k++) {
        float v[4] = {pxv[k], pyv[k], zv[k], iv[k]};
        for (int c = 0; c < 4; c++) {
            if (v[c] < mn[c]) mn[c] = v[c];
            if (v[c] > mx[c]) mx[c] = v[c];
        }
    }
    int last = nverts - 1;
    fprintf(log_file,
        "{\"frame\":%d,\"vertices\":%d,\"stream_checksum\":\"%016llx\","
        "\"vertex_minmax\":{\"px\":[%.9g,%.9g],\"py\":[%.9g,%.9g],"
        "\"z\":[%.9g,%.9g],\"i\":[%.9g,%.9g]},"
        "\"first_vertex\":[%.9g,%.9g,%.9g,%.9g],"
        "\"last_vertex\":[%.9g,%.9g,%.9g,%.9g],"
        "\"z_writes\":%llu,\"wireframe_pixels\":%llu,"
        "\"fb_checksum\":\"%016llx\",\"wall_ms\":%.3f}\n",
        frame, nverts, stream_checksum,
        mn[0], mx[0], mn[1], mx[1], mn[2], mx[2], mn[3], mx[3],
        pxv[0], pyv[0], zv[0], iv[0],
        pxv[last], pyv[last], zv[last], iv[last],
        log_z_writes, log_wireframe_pixels, log_fnv_fb(log_fnv_init()), wall_ms);
}

/* Wireframe overlay is part of doughnut.c's draw_triangle; the phase-2
 * protocol has no interactivity, so the host renders with it on (the host
 * owns rasterization policy; the canonical stream is unaffected). */
static int wireframe_on = 1;

static void generate_torus(void) {
    int idx = 0;
    for (int i = 0; i < U_STEPS; i++) {
        float u = (float)i / U_STEPS * 2.0f * (float)M_PI;
        float cu = cosf(u), su = sinf(u);

        for (int j = 0; j < V_STEPS; j++) {
            float v = (float)j / V_STEPS * 2.0f * (float)M_PI;
            float cv = cosf(v), sv = sinf(v);

            base_vertices[idx] = (Vector3){
                (R_MAJOR + R_MINOR * cv) * cu,
                (R_MAJOR + R_MINOR * cv) * su,
                R_MINOR * sv
            };

            base_normals[idx] = (Vector3){
                cv * cu,
                cv * su,
                sv
            };
            idx++;
        }
    }

    total_triangles = 0;
    for (int i = 0; i < U_STEPS; i++) {
        int next_i = (i + 1) % U_STEPS;
        for (int j = 0; j < V_STEPS; j++) {
            int next_j = (j + 1) % V_STEPS;

            int current = i * V_STEPS + j;
            int right = next_i * V_STEPS + j;
            int down = i * V_STEPS + next_j;
            int diag = next_i * V_STEPS + next_j;

            triangles[total_triangles++] = (Triangle){current, right, diag};
            triangles[total_triangles++] = (Triangle){current, diag, down};
        }
    }
}

/* Rasterizer with Gouraud shading interpolation and wireframe overlay - a
 * line-for-line port of doughnut.c's draw_triangle() with (x, y, z, int_)
 * taken from the streamed vertex data. */
static void draw_triangle(const Vertex *v0, const Vertex *v1, const Vertex *v2) {
    int min_x = (int)fmaxf(0, fminf(v0->x, fminf(v1->x, v2->x)));
    int max_x = (int)fminf(WIDTH - 1, fmaxf(v0->x, fmaxf(v1->x, v2->x)));
    int min_y = (int)fmaxf(0, fminf(v0->y, fminf(v1->y, v2->y)));
    int max_y = (int)fminf(HEIGHT - 1, fmaxf(v0->y, fmaxf(v1->y, v2->y)));

    float area = (v1->y - v2->y) * (v0->x - v2->x) + (v2->x - v1->x) * (v0->y - v2->y);
    if (fabsf(area) < 1e-5f) return;

    for (int y = min_y; y <= max_y; y++) {
        for (int x = min_x; x <= max_x; x++) {
            float px = (float)x + 0.5f;
            float py = (float)y + 0.5f;

            /* Barycentric coordinates */
            float w0 = ((v1->y - v2->y) * (px - v2->x) + (v2->x - v1->x) * (py - v2->y)) / area;
            float w1 = ((v2->y - v0->y) * (px - v2->x) + (v0->x - v2->x) * (py - v2->y)) / area;
            float w2 = 1.0f - w0 - w1;

            if (w0 >= 0.0f && w1 >= 0.0f && w2 >= 0.0f) {
                /* Perspective-correct depth interpolation */
                float inv_z = w0 * (1.0f / v0->z) + w1 * (1.0f / v1->z) + w2 * (1.0f / v2->z);
                float z = 1.0f / inv_z;

                int idx = y * WIDTH + x;
                if (z < zbuffer[idx]) {
                    zbuffer[idx] = z;
                    log_z_writes++;

                    /* Perspective-correct Gouraud intensity interpolation */
                    float intensity = (w0 * (v0->intensity / v0->z) + w1 * (v1->intensity / v1->z) + w2 * (v2->intensity / v2->z)) / inv_z;

                    if (wireframe_on && (w0 < 0.04f || w1 < 0.04f || w2 < 0.04f)) {
                        /* Cyan wireframe grid lines */
                        framebuffer[idx] = 0xFF00FFFF;
                        log_wireframe_pixels++;
                    } else {
                        /* Smooth shaded purple-pink gradient */
                        Uint32 r = (Uint32)(fminf(1.0f, intensity * 0.9f) * 255);
                        Uint32 g = (Uint32)(fminf(1.0f, intensity * 0.4f) * 255);
                        Uint32 b = (Uint32)(fminf(1.0f, intensity * 0.9f) * 255);
                        framebuffer[idx] = (0xFFu << 24) | (r << 16) | (g << 8) | b;
                    }
                }
            }
        }
    }
}

static void render_frame(const Vertex *verts, int nverts, int frame,
                         unsigned long long stream_checksum,
                         SDL_Renderer *ren, SDL_Texture *texture) {
    (void)nverts;
    log_z_writes = 0;
    log_wireframe_pixels = 0;
    Uint64 wt0 = SDL_GetPerformanceCounter();
    for (int i = 0; i < WIDTH * HEIGHT; i++) {
        zbuffer[i] = 1e9f;
        framebuffer[i] = 0xFF101010;
    }

    for (int t = 0; t < total_triangles; t++) {
        const Triangle *tri = &triangles[t];
        draw_triangle(&verts[tri->i0], &verts[tri->i1], &verts[tri->i2]);
    }

    double wms = log_wall_ms(wt0, SDL_GetPerformanceCounter());
    /* canonical log record: values as the rasterizer received them */
    {
        static float pxv[U_STEPS * V_STEPS], pyv[U_STEPS * V_STEPS],
                    zv[U_STEPS * V_STEPS], iv[U_STEPS * V_STEPS];
        for (int k = 0; k < nverts; k++) {
            pxv[k] = verts[k].x; pyv[k] = verts[k].y;
            zv[k] = verts[k].z; iv[k] = verts[k].intensity;
        }
        log_frame(frame, nverts, pxv, pyv, zv, iv, stream_checksum, wms);
    }

    SDL_UpdateTexture(texture, NULL, framebuffer, WIDTH * sizeof(Uint32));
    SDL_RenderClear(ren);
    SDL_RenderCopy(ren, texture, NULL, NULL);
    SDL_RenderPresent(ren);
}

int main(int argc, char **argv) {
    int present_limit = -1;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) present_limit = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--wireframe") && i + 1 < argc) wireframe_on = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--log") && i + 1 < argc) {
            log_file = fopen(argv[++i], "a");
            if (!log_file) { fprintf(stderr, "donut_host: cannot open log file\n"); return 1; }
        }
    }

    generate_torus();

    /* Token-stream protocol: F, 4 numbers per vertex, S. */
    Vertex *frames = NULL;
    unsigned long long *frame_checksums = NULL; /* raw-text FNV-1a per frame */
    int nframes = 0, frame_cap = 0;
    long total_vertices = 0, total_tri_drawn = 0;
    Vertex cur[U_STEPS * V_STEPS];
    unsigned long long cur_checksum = log_fnv_init(); /* raw-text FNV-1a */
    int cur_count = 0;
    char tok[32];
    while (scanf("%31s", tok) == 1) {
        if (tok[0] == 'F' && tok[1] == '\0') {
            cur_count = 0;
            cur_checksum = log_fnv_init();
        } else if (tok[0] == 'S' && tok[1] == '\0') {
            if (cur_count != U_STEPS * V_STEPS) {
                fprintf(stderr, "donut_host: frame %d has %d vertices, expected %d\n",
                        nframes, cur_count, U_STEPS * V_STEPS);
                return 2;
            }
            if (nframes == frame_cap) {
                frame_cap = frame_cap ? frame_cap * 2 : 16;
                frames = realloc(frames, (size_t)frame_cap * sizeof(cur));
                frame_checksums = realloc(frame_checksums, (size_t)frame_cap * sizeof(*frame_checksums));
                if (!frames || !frame_checksums) { fprintf(stderr, "donut_host: out of memory\n"); return 1; }
            }
            frame_checksums[nframes] = cur_checksum;
            memcpy(frames + (size_t)nframes * U_STEPS * V_STEPS, cur, sizeof(cur));
            nframes++;
            total_tri_drawn += total_triangles;
        } else {
            /* a vertex value: read the remaining three of its 4-tuple */
            Vertex v;
            char vtok[4][32];
            if (cur_count >= U_STEPS * V_STEPS) {
                fprintf(stderr, "donut_host: too many vertices in a frame\n");
                return 2;
            }
            if (sscanf(tok, "%f", &v.x) != 1) { fprintf(stderr, "donut_host: bad token %s\n", tok); return 2; }
            if (scanf("%31s %31s %31s", vtok[0], vtok[1], vtok[2]) != 3) { fprintf(stderr, "donut_host: bad vertex\n"); return 2; }
            if (sscanf(vtok[0], "%f", &v.y) != 1 || sscanf(vtok[1], "%f", &v.z) != 1
                || sscanf(vtok[2], "%f", &v.intensity) != 1) { fprintf(stderr, "donut_host: bad vertex\n"); return 2; }
            cur_checksum = log_fnv_text(cur_checksum, tok);
            cur_checksum = log_fnv_text(cur_checksum, vtok[0]);
            cur_checksum = log_fnv_text(cur_checksum, vtok[1]);
            cur_checksum = log_fnv_text(cur_checksum, vtok[2]);
            cur[cur_count++] = v;
            total_vertices++;
        }
    }
    if (nframes == 0) { fprintf(stderr, "donut_host: no frames in input\n"); return 2; }
    fprintf(stderr, "donut_host: %d frames, %ld vertices, %ld triangles per frame\n",
            nframes, total_vertices, total_tri_drawn / nframes);

    if (SDL_Init(SDL_INIT_VIDEO) != 0) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Window *win = SDL_CreateWindow("esolang torus - orbiting light",
                                       SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                       WIDTH, HEIGHT, SDL_WINDOW_SHOWN);
    if (!win) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!ren) ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
    if (!ren) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }
    SDL_Texture *texture = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                                             SDL_TEXTUREACCESS_STREAMING, WIDTH, HEIGHT);
    if (!texture) { fprintf(stderr, "donut_host: %s\n", SDL_GetError()); return 1; }

    int presented = 0;
    int running = 1;
    while (running) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) running = 0;
            if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_ESCAPE) running = 0;
        }
        render_frame(frames + (size_t)(presented % nframes) * U_STEPS * V_STEPS,
                     U_STEPS * V_STEPS, presented,
                     frame_checksums[presented % nframes], ren, texture);
        presented++;
        if (present_limit >= 0 && presented >= present_limit) running = 0;
        if (present_limit < 0) SDL_Delay(16);
    }

    SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
