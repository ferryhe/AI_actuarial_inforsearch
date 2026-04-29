"""
Tests for dynamic LLM model discovery.
"""

import os
import sys
import threading
import time
from unittest.mock import Mock, patch, MagicMock
import pytest

from ai_actuarial.llm_models import (
    ModelCache,
    get_model_cache,
    get_available_models,
    refresh_models,
    initialize_models,
    DEFAULT_MODELS,
)


class TestModelCache:
    """Test ModelCache class."""
    
    def test_initialization(self):
        """Test cache initialization."""
        cache = ModelCache(refresh_interval_hours=1)
        assert cache._models == {}
        assert cache._last_refresh is None
        assert not cache._initialized
    
    def test_get_models_all_providers(self):
        """Test getting models for all providers."""
        cache = ModelCache(refresh_interval_hours=1)
        
        # Mock the fetch methods to return defaults
        with patch.object(cache, '_fetch_openai_models', return_value=DEFAULT_MODELS['openai']), \
             patch.object(cache, '_fetch_mistral_models', return_value=DEFAULT_MODELS['mistral']), \
             patch.object(cache, '_fetch_siliconflow_models', return_value=DEFAULT_MODELS['siliconflow']):
            
            models = cache.get_models()
            
            assert 'openai' in models
            assert 'mistral' in models
            assert 'siliconflow' in models
            assert 'local' in models
            assert cache._initialized
            assert cache._last_refresh is not None
    
    def test_get_models_single_provider(self):
        """Test getting models for a specific provider."""
        cache = ModelCache(refresh_interval_hours=1)
        
        with patch.object(cache, '_fetch_openai_models', return_value=DEFAULT_MODELS['openai']), \
             patch.object(cache, '_fetch_mistral_models', return_value=DEFAULT_MODELS['mistral']), \
             patch.object(cache, '_fetch_siliconflow_models', return_value=DEFAULT_MODELS['siliconflow']):
            
            models = cache.get_models(provider='openai')
            
            assert 'openai' in models
            assert 'mistral' not in models
            assert len(models) == 1
    
    def test_force_refresh(self):
        """Test forcing a cache refresh."""
        cache = ModelCache(refresh_interval_hours=1)
        
        with patch.object(cache, '_perform_refresh') as mock_refresh:
            cache.force_refresh()
            mock_refresh.assert_called_once()
    
    def test_thread_safety(self):
        """Test that cache is thread-safe."""
        cache = ModelCache(refresh_interval_hours=1)
        results = []
        
        def get_models():
            models = cache.get_models()
            results.append(models)
        
        # Patch fetch methods once, outside the threads
        with patch.object(cache, '_fetch_openai_models', return_value=DEFAULT_MODELS['openai']), \
             patch.object(cache, '_fetch_mistral_models', return_value=DEFAULT_MODELS['mistral']), \
             patch.object(cache, '_fetch_siliconflow_models', return_value=DEFAULT_MODELS['siliconflow']):
            
            threads = [threading.Thread(target=get_models) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        
        # All threads should get the same result
        assert len(results) == 5
        assert all(r == results[0] for r in results)


class TestOpenAIModelFetching:
    """Test OpenAI model fetching."""
    
    def test_fetch_openai_models_success(self):
        """Test successful OpenAI model fetching."""
        cache = ModelCache()
        
        # Mock OpenAI client
        mock_model = Mock()
        mock_model.id = "gpt-4o"
        
        mock_response = Mock()
        mock_response.data = [mock_model]
        
        mock_client = Mock()
        mock_client.models.list.return_value = mock_response
        
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch.dict(sys.modules, {'openai': mock_openai}):
            
            models = cache._fetch_openai_models()
            
            assert len(models) > 0
            assert any(m['name'] == 'gpt-4o' for m in models)
    
    def test_fetch_openai_models_no_api_key(self):
        """Test OpenAI fetching with no API key."""
        cache = ModelCache()
        
        with patch.dict(os.environ, {}, clear=True):
            models = cache._fetch_openai_models()
            
            # Should return defaults
            assert models == DEFAULT_MODELS['openai']
    
    def test_fetch_openai_models_api_error(self):
        """Test OpenAI fetching with API error."""
        cache = ModelCache()
        
        mock_client = Mock()
        mock_client.models.list.side_effect = Exception("API Error")
        
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch.dict(sys.modules, {'openai': mock_openai}):
            
            models = cache._fetch_openai_models()
            
            # Should return defaults on error
            assert models == DEFAULT_MODELS['openai']


class TestMistralModelFetching:
    """Test Mistral model fetching."""
    
    def test_fetch_mistral_models_success(self):
        """Test successful Mistral model fetching."""
        cache = ModelCache()
        
        # Mock Mistral client
        mock_model = Mock()
        mock_model.id = "pixtral-12b-2409"
        
        mock_response = Mock()
        mock_response.data = [mock_model]
        
        mock_client = Mock()
        mock_client.models.list.return_value = mock_response
        
        mock_mistral = MagicMock()
        mock_mistral.Mistral.return_value = mock_client
        
        with patch.dict(os.environ, {'MISTRAL_API_KEY': 'test-key'}), \
             patch.dict(sys.modules, {'mistralai': mock_mistral}):
            
            models = cache._fetch_mistral_models()
            
            assert len(models) > 0
            assert any(m['name'] == 'pixtral-12b-2409' for m in models)
    
    def test_fetch_mistral_models_no_api_key(self):
        """Test Mistral fetching with no API key."""
        cache = ModelCache()
        
        with patch.dict(os.environ, {}, clear=True):
            models = cache._fetch_mistral_models()
            
            # Should return defaults
            assert models == DEFAULT_MODELS['mistral']


class TestSiliconFlowModelFetching:
    """Test SiliconFlow model fetching."""
    
    def test_fetch_siliconflow_models_success(self):
        """Test successful SiliconFlow model fetching."""
        cache = ModelCache()
        
        # Mock OpenAI-compatible client
        mock_model = Mock()
        mock_model.id = "deepseek-ai/DeepSeek-OCR"
        
        mock_response = Mock()
        mock_response.data = [mock_model]
        
        mock_client = Mock()
        mock_client.models.list.return_value = mock_response
        
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        
        with patch.dict(os.environ, {'SILICONFLOW_API_KEY': 'test-key'}), \
             patch.dict(sys.modules, {'openai': mock_openai}):
            
            models = cache._fetch_siliconflow_models()
            
            assert len(models) > 0
            assert any(m['name'] == 'deepseek-ai/DeepSeek-OCR' for m in models)
    
    def test_fetch_siliconflow_models_no_api_key(self):
        """Test SiliconFlow fetching with no API key."""
        cache = ModelCache()
        
        with patch.dict(os.environ, {}, clear=True):
            models = cache._fetch_siliconflow_models()
            
            # Should return defaults
            assert models == DEFAULT_MODELS['siliconflow']


class TestGlobalAPI:
    """Test global API functions."""
    
    def test_get_model_cache_singleton(self):
        """Test that get_model_cache returns singleton."""
        cache1 = get_model_cache()
        cache2 = get_model_cache()
        
        assert cache1 is cache2
    
    def test_get_available_models(self):
        """Test get_available_models function."""
        with patch('ai_actuarial.llm_models.ModelCache') as mock_cache_class:
            mock_cache = Mock()
            mock_cache.get_models.return_value = DEFAULT_MODELS
            mock_cache_class.return_value = mock_cache
            
            # Reset the global cache
            import ai_actuarial.llm_models as llm_models
            llm_models._model_cache = None
            
            models = get_available_models()
            
            assert 'openai' in models
            assert 'local' in models
    
    def test_refresh_models(self):
        """Test refresh_models function."""
        with patch('ai_actuarial.llm_models.ModelCache') as mock_cache_class:
            mock_cache = Mock()
            mock_cache_class.return_value = mock_cache
            
            # Reset the global cache
            import ai_actuarial.llm_models as llm_models
            llm_models._model_cache = None
            
            refresh_models()
            
            mock_cache.force_refresh.assert_called_once()
    
    def test_initialize_models(self):
        """Test initialize_models function."""
        with patch('ai_actuarial.llm_models.ModelCache') as mock_cache_class:
            mock_cache = Mock()
            mock_cache.get_models.return_value = DEFAULT_MODELS
            mock_cache_class.return_value = mock_cache
            
            # Reset the global cache
            import ai_actuarial.llm_models as llm_models
            llm_models._model_cache = None
            
            initialize_models()
            
            mock_cache.get_models.assert_called_once()


class TestDefaultModels:
    """Test that default models are properly structured."""
    
    def test_default_models_structure(self):
        """Test that DEFAULT_MODELS has correct structure."""
        assert 'openai' in DEFAULT_MODELS
        assert 'mistral' in DEFAULT_MODELS
        assert 'siliconflow' in DEFAULT_MODELS
        assert 'local' in DEFAULT_MODELS
        assert 'mathpix' in DEFAULT_MODELS
        
        for provider, models in DEFAULT_MODELS.items():
            assert isinstance(models, list)
            for model in models:
                assert 'name' in model
                assert 'display_name' in model
                assert 'types' in model
                assert isinstance(model['types'], list)
                assert len(model['types']) > 0

    def test_recommended_markdown_tools_are_available_as_ocr_models(self):
        local_ocr_names = {model["name"] for model in DEFAULT_MODELS["local"] if "ocr" in model["types"]}
        mathpix_ocr_names = {model["name"] for model in DEFAULT_MODELS["mathpix"] if "ocr" in model["types"]}

        assert {"opendataloader", "markitdown", "docling"}.issubset(local_ocr_names)
        assert "mathpix" in mathpix_ocr_names
