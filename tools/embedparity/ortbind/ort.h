#ifndef TROVE_ORT_H
#define TROVE_ORT_H
#include <stddef.h>
#include <stdint.h>

typedef struct OrtSessionHandle OrtSessionHandle;

int ort_init(void);
const char *ort_last_error(void);
OrtSessionHandle *ort_open(const char *model_path, int intra_threads);
size_t ort_input_count(OrtSessionHandle *h);
const char *ort_input_name(OrtSessionHandle *h, size_t index);
size_t ort_output_count(OrtSessionHandle *h);
const char *ort_output_name(OrtSessionHandle *h, size_t index);

/* Runs the text encoder. Writes seq*768 floats into out_hidden. */
int ort_run_text(OrtSessionHandle *h, const int64_t *input_ids, const int64_t *token_type_ids,
                 const int64_t *attention_mask, int64_t seq, float *out_hidden, size_t out_cap,
                 size_t *out_written);

/* Runs the vision encoder. Writes 197*768 floats into out_hidden. */
int ort_run_vision(OrtSessionHandle *h, const float *pixel_values, size_t pixel_count,
                   float *out_hidden, size_t out_cap, size_t *out_written);

#endif
