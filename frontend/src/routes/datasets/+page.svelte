<script>
  import { onMount } from 'svelte';

  let datasets = [];
  let loading = true;
  let page = 1;
  let totalPages = 1;
  let total = 0;

  async function loadDatasets() {
    loading = true;
    try {
      const res = await fetch(`/api/datasets?page=${page}&page_size=20`);
      const data = await res.json();
      datasets = data.items || [];
      totalPages = data.total_pages;
      total = data.total;
    } catch (err) {
      console.error('Failed to load datasets:', err);
    } finally {
      loading = false;
    }
  }

  onMount(loadDatasets);

  function nextPage() {
    if (page < totalPages) {
      page++;
      loadDatasets();
    }
  }

  function prevPage() {
    if (page > 1) {
      page--;
      loadDatasets();
    }
  }
</script>

<div>
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold text-gray-800">Browse Datasets</h1>
    <span class="text-gray-500">{total} datasets</span>
  </div>

  {#if loading}
    <div class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
    </div>
  {:else}
    <div class="space-y-3">
      {#each datasets as dataset}
        
          href="/datasets/{dataset.identifier}"
          class="block bg-white rounded-lg shadow-sm border hover:shadow-md transition-shadow p-4"
        >
          <h2 class="font-semibold text-gray-800 hover:text-green-700">
            {dataset.title}
          </h2>
          <p class="text-gray-600 text-sm mt-1 line-clamp-2">
            {dataset.abstract}
          </p>
        </a>
      {/each}
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-center gap-4 mt-8">
      <button
        on:click={prevPage}
        disabled={page === 1}
        class="px-4 py-2 border rounded disabled:opacity-50"
      >
        ← Previous
      </button>
      <span class="text-gray-600">Page {page} of {totalPages}</span>
      <button
        on:click={nextPage}
        disabled={page === totalPages}
        class="px-4 py-2 border rounded disabled:opacity-50"
      >
        Next →
      </button>
    </div>
  {/if}
</div>