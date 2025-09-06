
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef struct Arena {
  unsigned char* base;
  size_t cap;
  size_t used;
} Arena;

Arena* arena_new(size_t cap){
  Arena* a = (Arena*)malloc(sizeof(Arena));
  a->base = (unsigned char*)malloc(cap);
  a->cap = cap; a->used = 0; return a;
}

void* arena_alloc(Arena* a, size_t n){
  if(a->used + n > a->cap) return NULL;
  void* p = a->base + a->used; a->used += n; return p;
}

void arena_free(Arena* a){
  if(!a) return;
  free(a->base); free(a);
}

int main(){
  Arena* a = arena_new(1024);
  char* s = (char*)arena_alloc(a, 6);
  if(!s){ puts("alloc fail"); return 1; }
  memcpy(s, "hello", 6);
  printf("%s\n", s);
  arena_free(a);
  return 0;
}
