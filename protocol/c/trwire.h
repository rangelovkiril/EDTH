/* trwire.h — Triangulum wire protocol v1. Normative spec: docs/protocol.md */
#ifndef TRWIRE_H
#define TRWIRE_H

#include <stdint.h>
#include <string.h>

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "trwire assumes a little-endian target"
#endif

#define TR_MAGIC0 'T'
#define TR_MAGIC1 'R'
#define TR_VERSION 1

#define TR_PORT_INGEST 5600
#define TR_PORT_TSYNC 5601

enum tr_msg_type {
    TR_MSG_DETECTION_BATCH = 0x01,
    TR_MSG_STATUS = 0x02,
    TR_MSG_TSYNC_REQ = 0x10,
    TR_MSG_TSYNC_RESP = 0x11,
};

#define TR_FLAG_TIME_SYNCED 0x01u
#define TR_FLAG_TEST 0x02u

#define TR_MAX_DETECTIONS 16
#define TR_SYNC_AGE_NEVER 0xFFFFFFFFu
#define TR_TEMP_NA (-128)
#define TR_MAX_MSG_SIZE 220

typedef struct __attribute__((packed)) {
    char magic[2];
    uint8_t version;
    uint8_t type;
    uint8_t node_id;
    uint8_t flags;
    uint16_t seq;
} tr_header_t;

typedef struct __attribute__((packed)) {
    uint16_t cx_q3; /* centroid x * 8 */
    uint16_t cy_q3; /* centroid y * 8 */
    uint16_t w;
    uint16_t h;
    uint16_t area;   /* saturating */
    uint8_t conf;    /* confidence * 255 */
    uint8_t reserved;
} tr_detection_t;

typedef struct __attribute__((packed)) {
    tr_header_t hdr;
    uint64_t t_capture_us;
    uint32_t frame_id;
    uint16_t width;
    uint16_t height;
    uint8_t count;
    uint8_t reserved[3];
    tr_detection_t det[TR_MAX_DETECTIONS];
} tr_detection_batch_t;

typedef struct __attribute__((packed)) {
    tr_header_t hdr;
    uint32_t uptime_ms;
    uint32_t sync_age_ms;
    int32_t clock_offset_us;
    uint32_t rtt_us;
    uint16_t fps_x10;
    uint16_t dropped_frames;
    int8_t rssi_dbm;
    int8_t temp_c;
    uint8_t reserved[2];
} tr_status_t;

typedef struct __attribute__((packed)) {
    tr_header_t hdr;
    uint64_t t1_us;
} tr_tsync_req_t;

typedef struct __attribute__((packed)) {
    tr_header_t hdr;
    uint64_t t1_us;
    uint64_t t2_us;
    uint64_t t3_us;
} tr_tsync_resp_t;

_Static_assert(sizeof(tr_header_t) == 8, "header size");
_Static_assert(sizeof(tr_detection_t) == 12, "detection size");
_Static_assert(sizeof(tr_detection_batch_t) == 28 + 12 * TR_MAX_DETECTIONS, "batch size");
_Static_assert(sizeof(tr_detection_batch_t) == TR_MAX_MSG_SIZE, "max msg size");
_Static_assert(sizeof(tr_status_t) == 32, "status size");
_Static_assert(sizeof(tr_tsync_req_t) == 16, "tsync req size");
_Static_assert(sizeof(tr_tsync_resp_t) == 32, "tsync resp size");

static inline void tr_header_init(tr_header_t *h, uint8_t type, uint8_t node_id,
                                  uint8_t flags, uint16_t seq)
{
    h->magic[0] = TR_MAGIC0;
    h->magic[1] = TR_MAGIC1;
    h->version = TR_VERSION;
    h->type = type;
    h->node_id = node_id;
    h->flags = flags;
    h->seq = seq;
}

/* Bytes to send for a batch with b->count detections. */
static inline size_t tr_detection_batch_size(const tr_detection_batch_t *b)
{
    return 28u + 12u * (size_t)b->count;
}

/* Saturating helpers for filling detections. */
static inline uint16_t tr_q3(float px)
{
    float v = px * 8.0f + 0.5f;
    if (v < 0.0f) return 0;
    if (v > 65535.0f) return 65535;
    return (uint16_t)v;
}

static inline uint8_t tr_conf_u8(float conf)
{
    float v = conf * 255.0f + 0.5f;
    if (v < 0.0f) return 0;
    if (v > 255.0f) return 255;
    return (uint8_t)v;
}

#endif /* TRWIRE_H */
