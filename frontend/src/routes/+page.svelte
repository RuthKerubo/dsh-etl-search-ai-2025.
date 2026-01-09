<script>
  let query = '';
  let results = [];
  let loading = false;
  let searchMode = '';
  let searched = false;

  async function search() {
    if (!query.trim()) return;
    
    loading = true;
    searched = true;
    
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=20`);
      const data = await res.json();
      results = data.results || [];
      searchMode = data.mode;
    } catch (err) {
      console.error('Search failed:', err);
      results = [];
    } finally {
      loading = false;
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Enter') search();
  }
</script>

<div class="max-w-4xl mx-auto">
  <!-- Search Box -->
  <div class="text-center mb-8">
    <h1 class="text-3xl font-bold text-gray-800 mb-4">
      Search Environmental Datasets
    </h1>
    <p class="text-gray-600 mb-6">
      Search 200+ datasets from the UK Centre for Ecology & Hydrology
    </p>
    
    <div class="flex gap-2 max-w-2xl mx-auto">
      <input
        type="text"
        bind:value={query}
        on:keydown={handleKeydown}
        placeholder="e.g., climate change, water quality, biodiversity..."
        class="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent outline-none"
      />
      <button
        on:click={search}
        disabled={loading}
        class="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
      >
        {loading ? 'Searching...' : 'Search'}
      </button>
    </div>
    
    {#if searchMode}
      <p class="text-sm text-gray-500 mt-2">
        Mode: {searchMode} • {results.length} results
      </p>
    {/if}
  </div>

  <!-- Results -->
  {#if loading}
    <div class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
      <p class="mt-4 text-gray-600">Searching...</p>
    </div>
  {:else if searched && results.length === 0}
    <div class="text-center py-12 text-gray-500">
      No results found for "{query}"
    </div>
  {:else if results.length > 0}
    <div class="space-y-4">
      {#each results as result, i}
        <a
            href="/datasets/{result.identifier}"
            class="block bg-white rounded-lg shadow-sm border hover:shadow-md transition-shadow p-4"
        >
            <div class="flex items-start justify-between">
            <div class="flex-1">
                <h2 class="text-lg font-semibold text-gray-800 hover:text-green-700">
                {result.title}
                </h2>

                <p class="text-gray-600 text-sm mt-1 line-clamp-2">
                {result.abstract}
                </p>

                {#if result.keywords?.length > 0}
                <div class="flex flex-wrap gap-1 mt-2">
                    {#each result.keywords.slice(0, 5) as keyword}
                    <span class="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded">
                        {keyword}
                    </span>
                    {/each}
                </div>
                {/if}
            </div>

            <div class="ml-4 text-right">
                <span class="text-sm font-medium text-green-600">
                {(result.score * 100).toFixed(0)}%
                </span>

                <div class="text-xs text-gray-400 mt-1">
                {#if result.from_semantic && result.from_keyword}
                    Hybrid
                {:else if result.from_semantic}
                    Semantic
                {:else}
                    Keyword
                {/if}
                </div>
            </div>
            </div>
        </a>
        {/each}
    </div>
  {/if}
</div>