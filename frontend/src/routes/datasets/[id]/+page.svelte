<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';

  let dataset = null;
  let loading = true;
  let error = null;

  onMount(async () => {
    try {
      const res = await fetch(`/api/datasets/${$page.params.id}`);
      if (!res.ok) throw new Error('Dataset not found');
      dataset = await res.json();
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  });
</script>

<div class="max-w-4xl mx-auto">
  {#if loading}
    <div class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
    </div>
  {:else if error}
    <div class="text-center py-12">
      <p class="text-red-600">{error}</p>
      <a href="/datasets" class="text-green-600 hover:underline mt-4 inline-block">
        ← Back to datasets
      </a>
    </div>
  {:else if dataset}
    <div class="bg-white rounded-lg shadow-sm border p-6">
      <a href="/datasets" class="text-green-600 hover:underline text-sm">
        ← Back to datasets
      </a>
      
      <h1 class="text-2xl font-bold text-gray-800 mt-4">{dataset.title}</h1>
      
      {#if dataset.keywords?.length > 0}
        <div class="flex flex-wrap gap-2 mt-3">
          {#each dataset.keywords as keyword}
            <span class="px-2 py-1 bg-green-100 text-green-700 text-sm rounded">
              {keyword}
            </span>
          {/each}
        </div>
      {/if}
      
      <div class="mt-6">
        <h2 class="font-semibold text-gray-700 mb-2">Abstract</h2>
        <p class="text-gray-600 whitespace-pre-line">{dataset.abstract}</p>
      </div>
      
      {#if dataset.temporal_extent}
        <div class="mt-6">
          <h2 class="font-semibold text-gray-700 mb-2">Temporal Coverage</h2>
          <p class="text-gray-600">
            {dataset.temporal_extent.start || 'Unknown'} — {dataset.temporal_extent.end || 'Present'}
          </p>
        </div>
      {/if}
      
      {#if dataset.bounding_box}
        <div class="mt-6">
          <h2 class="font-semibold text-gray-700 mb-2">Spatial Coverage</h2>
          <p class="text-gray-600 text-sm">
            West: {dataset.bounding_box.west}°, 
            East: {dataset.bounding_box.east}°, 
            South: {dataset.bounding_box.south}°, 
            North: {dataset.bounding_box.north}°
          </p>
        </div>
      {/if}
      
      <div class="mt-6 pt-4 border-t">
        <p class="text-xs text-gray-400">ID: {dataset.identifier}</p>
      </div>
    </div>
  {/if}
</div>