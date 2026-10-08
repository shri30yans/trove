#include "ort.h"
#include "onnxruntime_c_api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const OrtApi *g_ort = NULL;
static OrtEnv *g_env = NULL;
static OrtMemoryInfo *g_mem = NULL;
static char g_err[1024];

static void set_err(const char *what, OrtStatus *s) {
  if (s) {
    snprintf(g_err, sizeof g_err, "%s: %s", what, g_ort->GetErrorMessage(s));
    g_ort->ReleaseStatus(s);
  } else {
    snprintf(g_err, sizeof g_err, "%s", what);
  }
}

static OrtStatus *plain(const char *msg) {
  snprintf(g_err, sizeof g_err, "%s", msg);
  return NULL;
}

struct OrtSessionHandle {
  OrtSession *session;
  char *names[8];
  size_t num_inputs;
  char *out_names[8];
  size_t num_outputs;
};

int ort_init(void) {
  const OrtApiBase *base = OrtGetApiBase();
  g_ort = base->GetApi(ORT_API_VERSION);
  if (!g_ort) { plain("GetApi returned NULL"); return -1; }
  OrtStatus *s = g_ort->CreateEnv(ORT_LOGGING_LEVEL_FATAL, "trove-probe", &g_env);
  if (s) { set_err("CreateEnv", s); return -1; }
  s = g_ort->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &g_mem);
  if (s) { set_err("CreateCpuMemoryInfo", s); return -1; }
  return 0;
}

const char *ort_last_error(void) { return g_err; }

OrtSessionHandle *ort_open(const char *model_path, int intra_threads) {
  OrtStatus *s;
  OrtSessionOptions *options = NULL;
  OrtSession *session = NULL;
  s = g_ort->CreateSessionOptions(&options);
  if (s) { set_err("CreateSessionOptions", s); return NULL; }
  if (intra_threads > 0) {
    s = g_ort->SetIntraOpNumThreads(options, intra_threads);
    if (s) g_ort->ReleaseStatus(s);
  }
  s = g_ort->CreateSession(g_env, model_path, options, &session);
  g_ort->ReleaseSessionOptions(options);
  if (s) { set_err("CreateSession", s); return NULL; }

  OrtAllocator *allocator = NULL;
  s = g_ort->GetAllocatorWithDefaultOptions(&allocator);
  if (s) { set_err("GetAllocatorWithDefaultOptions", s); return NULL; }

  struct OrtSessionHandle *h = calloc(1, sizeof *h);
  s = g_ort->SessionGetInputCount(session, &h->num_inputs);
  if (s) { set_err("SessionGetInputCount", s); free(h); return NULL; }
  if (h->num_inputs > 8) { free(h); plain("more than 8 inputs"); return NULL; }
  for (size_t i = 0; i < h->num_inputs; i++) {
    char *raw = NULL;
    s = g_ort->SessionGetInputName(session, i, allocator, &raw);
    if (s) { set_err("SessionGetInputName", s); return NULL; }
    h->names[i] = strdup(raw);
    allocator->Free(allocator, raw);
  }
  s = g_ort->SessionGetOutputCount(session, &h->num_outputs);
  if (s) { set_err("SessionGetOutputCount", s); return NULL; }
  if (h->num_outputs > 8) { free(h); plain("more than 8 outputs"); return NULL; }
  for (size_t i = 0; i < h->num_outputs; i++) {
    char *raw = NULL;
    s = g_ort->SessionGetOutputName(session, i, allocator, &raw);
    if (s) { set_err("SessionGetOutputName", s); return NULL; }
    h->out_names[i] = strdup(raw);
    allocator->Free(allocator, raw);
  }
  h->session = session;
  return (OrtSessionHandle *)h;
}

size_t ort_input_count(OrtSessionHandle *h) { return h->num_inputs; }
const char *ort_input_name(OrtSessionHandle *h, size_t index) { return h->names[index]; }
size_t ort_output_count(OrtSessionHandle *h) { return h->num_outputs; }
const char *ort_output_name(OrtSessionHandle *h, size_t index) { return h->out_names[index]; }

static OrtValue *int64_tensor(const int64_t *data, size_t elements, int64_t rows, int64_t cols) {
  int64_t shape[2] = {rows, cols};
  OrtValue *out = NULL;
  OrtStatus *s = g_ort->CreateTensorWithDataAsOrtValue(
      g_mem, (void *)data, elements * sizeof(int64_t), shape, 2,
      ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &out);
  if (s) { set_err("CreateTensorWithDataAsOrtValue(int64)", s); return NULL; }
  return out;
}

static int read_floats(OrtValue *value, float *buffer, size_t capacity, size_t *written) {
  OrtTensorTypeAndShapeInfo *info = NULL;
  OrtStatus *s = g_ort->GetTensorTypeAndShape(value, &info);
  if (s) { set_err("GetTensorTypeAndShapeInfo", s); return -1; }
  size_t rank = 0;
  s = g_ort->GetDimensionsCount(info, &rank);
  if (s) { set_err("GetDimensionsCount", s); return -1; }
  int64_t dims[8] = {0};
  if (rank > 8) { g_ort->ReleaseTensorTypeAndShapeInfo(info); plain("rank > 8"); return -1; }
  s = g_ort->GetDimensions(info, dims, rank);
  g_ort->ReleaseTensorTypeAndShapeInfo(info);
  if (s) { set_err("GetDimensions", s); return -1; }
  size_t elements = 1;
  for (size_t i = 0; i < rank; i++) elements *= (size_t)dims[i];
  if (elements > capacity) { plain("output larger than buffer"); return -1; }
  void *data = NULL;
  s = g_ort->GetTensorMutableData(value, &data);
  if (s) { set_err("GetTensorMutableData", s); return -1; }
  memcpy(buffer, data, elements * sizeof(float));
  *written = elements;
  return 0;
}

/* Runs the text encoder. Any of the three optional inputs is fed only if the graph declares it. */
int ort_run_text(OrtSessionHandle *hh, const int64_t *input_ids, const int64_t *token_type_ids,
                 const int64_t *attention_mask, int64_t seq, float *hidden, size_t hidden_capacity,
                 size_t *hidden_written) {
  struct OrtSessionHandle *h = (struct OrtSessionHandle *)hh;
  const int64_t *sources[3];
  const char *wanted[3] = {"input_ids", "token_type_ids", "attention_mask"};
  sources[0] = input_ids; sources[1] = token_type_ids; sources[2] = attention_mask;

  OrtValue *values[3]; const char *names[3]; size_t n = 0;
  for (size_t s = 0; s < h->num_inputs; s++) {
    const char *graph_name = h->names[s];
    const int64_t *src = NULL;
    for (int w = 0; w < 3; w++) if (strcmp(graph_name, wanted[w]) == 0) src = sources[w];
    if (!src) { plain("graph wants an input this probe cannot supply"); return -1; }
    values[n] = int64_tensor(src, (size_t)seq, 1, seq);
    if (!values[n]) return -1;
    names[n] = graph_name;
    n++;
  }
  const char *output_names[1] = {h->out_names[0]};
  OrtValue *outputs[1] = {NULL};
  OrtStatus *s = g_ort->Run(h->session, NULL, names, (const OrtValue *const *)values, n, output_names, 1, outputs);
  for (size_t i = 0; i < n; i++) g_ort->ReleaseValue(values[i]);
  if (s) { set_err("Run(text)", s); return -1; }
  int rc = read_floats(outputs[0], hidden, hidden_capacity, hidden_written);
  g_ort->ReleaseValue(outputs[0]);
  return rc;
}

int ort_run_vision(OrtSessionHandle *hh, const float *pixels, size_t pixel_count, float *hidden,
                   size_t hidden_capacity, size_t *hidden_written) {
  struct OrtSessionHandle *h = (struct OrtSessionHandle *)hh;
  if (h->num_inputs != 1) { plain("vision graph expected one input"); return -1; }
  int64_t shape[4] = {1, 3, 224, 224};
  OrtValue *input = NULL;
  OrtStatus *s = g_ort->CreateTensorWithDataAsOrtValue(
      g_mem, (void *)pixels, pixel_count * sizeof(float), shape, 4,
      ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &input);
  if (s) { set_err("CreateTensorWithDataAsOrtValue(float)", s); return -1; }
  const char *names[1] = {h->names[0]};
  const char *output_names[1] = {h->out_names[0]};
  OrtValue *outputs[1] = {NULL};
  s = g_ort->Run(h->session, NULL, names, (const OrtValue* const*)&input, 1, output_names, 1, outputs);
  g_ort->ReleaseValue(input);
  if (s) { set_err("Run(vision)", s); return -1; }
  int rc = read_floats(outputs[0], hidden, hidden_capacity, hidden_written);
  g_ort->ReleaseValue(outputs[0]);
  return rc;
}
