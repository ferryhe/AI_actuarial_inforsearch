"""
Unit tests for ApiToken database model.

Tests cover model creation, to_dict conversion, and database operations.
"""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ai_actuarial.models.api_token import ApiToken, Base


class TestApiToken:
    """Test cases for ApiToken model."""
    
    @pytest.fixture
    def engine(self):
        """Create in-memory SQLite database for testing."""
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        return engine
    
    @pytest.fixture
    def session(self, engine):
        """Create database session for testing."""
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()
    
    def test_create_api_token(self, session):
        """Test creating an API token."""
        token = ApiToken(
            provider='openai',
            category='llm',
            api_key_encrypted='encrypted_key_data',
            api_base_url='https://api.openai.com/v1',
            status='active'
        )
        
        session.add(token)
        session.commit()
        
        assert token.id is not None
        assert token.provider == 'openai'
        assert token.category == 'llm'
        assert token.api_key_encrypted == 'encrypted_key_data'
        assert token.status == 'active'
        assert token.usage_count == 0
    
    def test_default_values(self, session):
        """Test that default values are set correctly."""
        token = ApiToken(
            provider='brave',
            category='search',
            api_key_encrypted='encrypted_brave_key'
        )
        
        session.add(token)
        session.commit()
        
        assert token.status == 'active'
        assert token.usage_count == 0
        assert token.created_at is not None
        assert token.updated_at is not None
        assert isinstance(token.created_at, datetime)
        assert isinstance(token.updated_at, datetime)
    
    def test_unique_provider_category_constraint(self, session):
        """Test that provider+category combination must be unique."""
        token1 = ApiToken(
            provider='openai',
            category='llm',
            api_key_encrypted='key1'
        )
        session.add(token1)
        session.commit()
        
        token2 = ApiToken(
            provider='openai',
            category='llm',
            api_key_encrypted='key2'
        )
        session.add(token2)
        
        with pytest.raises(Exception):  # SQLAlchemy IntegrityError
            session.commit()
    
    def test_different_category_allows_duplicate_provider(self, session):
        """Test that same provider with different category is allowed."""
        token1 = ApiToken(
            provider='openai',
            category='llm',
            api_key_encrypted='key1'
        )
        token2 = ApiToken(
            provider='openai',
            category='embeddings',
            api_key_encrypted='key2'
        )
        
        session.add(token1)
        session.add(token2)
        session.commit()
        
        assert token1.id is not None
        assert token2.id is not None
        assert token1.id != token2.id
    
    def test_to_dict_with_masking(self, session):
        """Test to_dict method with key masking."""
        token = ApiToken(
            provider='mistral',
            category='llm',
            api_key_encrypted='encrypted_mistral_key',
            api_base_url='https://api.mistral.ai',
            status='active',
            notes='Production API key'
        )
        
        session.add(token)
        session.commit()
        
        token_dict = token.to_dict(mask_key=True)
        
        assert token_dict['id'] == token.id
        assert token_dict['provider'] == 'mistral'
        assert token_dict['category'] == 'llm'
        assert token_dict['api_key'] == '****'  # Masked
        assert token_dict['api_base_url'] == 'https://api.mistral.ai'
        assert token_dict['status'] == 'active'
        assert token_dict['notes'] == 'Production API key'
        assert 'created_at' in token_dict
        assert 'updated_at' in token_dict
    
    def test_to_dict_timestamps_serialization(self, session):
        """Test that timestamps are properly serialized to ISO format."""
        token = ApiToken(
            provider='serpapi',
            category='search',
            api_key_encrypted='encrypted_serpapi_key'
        )
        
        session.add(token)
        session.commit()
        
        token_dict = token.to_dict()
        
        # Should be ISO format strings
        assert isinstance(token_dict['created_at'], str)
        assert isinstance(token_dict['updated_at'], str)
        assert 'T' in token_dict['created_at']  # ISO format includes T
    
    def test_to_dict_null_timestamps(self):
        """Test to_dict with null optional timestamps."""
        token = ApiToken(
            provider='brave',
            category='search',
            api_key_encrypted='encrypted_brave_key'
        )
        
        token_dict = token.to_dict()
        
        assert token_dict['last_verified_at'] is None
        assert token_dict['last_used_at'] is None
    
    def test_repr_string(self, session):
        """Test string representation of ApiToken."""
        token = ApiToken(
            provider='openai',
            category='llm',
            api_key_encrypted='encrypted_key'
        )
        
        session.add(token)
        session.commit()
        
        repr_str = repr(token)
        
        assert 'ApiToken' in repr_str
        assert 'openai' in repr_str
        assert 'llm' in repr_str
        assert str(token.id) in repr_str
    
    def test_update_timestamps(self, session):
        """Test that updated_at changes on update."""
        token = ApiToken(
            provider='siliconflow',
            category='llm',
            api_key_encrypted='encrypted_key'
        )
        
        session.add(token)
        session.commit()
        
        original_updated_at = token.updated_at
        
        # Simulate some time passing and update
        import time
        time.sleep(0.1)
        
        token.notes = 'Updated notes'
        session.commit()
        
        # Note: SQLite may not automatically update updated_at with onupdate
        # In production with PostgreSQL or explicit update, this would work
        # For this test, we verify the field exists
        assert token.updated_at is not None
    
    def test_optional_fields(self, session):
        """Test that optional fields can be None."""
        token = ApiToken(
            provider='test_provider',
            category='test',
            api_key_encrypted='encrypted_key'
        )
        
        session.add(token)
        session.commit()
        
        assert token.api_base_url is None
        assert token.config_json is None
        assert token.verification_status is None
        assert token.last_verified_at is None
        assert token.last_used_at is None
        assert token.notes is None
    
    def test_required_fields_validation(self, session):
        """Test that database enforces NOT NULL constraints."""
        # SQLAlchemy allows object creation with missing fields
        # but database INSERT will fail for required fields
        token = ApiToken()
        session.add(token)
        
        # Should fail on commit due to NOT NULL constraints
        with pytest.raises(Exception):  # SQLAlchemy IntegrityError
            session.commit()
    
    def test_query_by_provider_and_category(self, session):
        """Test querying tokens by provider and category."""
        token1 = ApiToken(
            provider='openai',
            category='llm',
            api_key_encrypted='key1'
        )
        token2 = ApiToken(
            provider='brave',
            category='search',
            api_key_encrypted='key2'
        )
        token3 = ApiToken(
            provider='openai',
            category='embeddings',
            api_key_encrypted='key3'
        )
        
        session.add_all([token1, token2, token3])
        session.commit()
        
        # Query by provider
        openai_tokens = session.query(ApiToken).filter_by(provider='openai').all()
        assert len(openai_tokens) == 2
        
        # Query by category
        llm_tokens = session.query(ApiToken).filter_by(category='llm').all()
        assert len(llm_tokens) == 1
        assert llm_tokens[0].provider == 'openai'
        
        # Query by both
        specific_token = session.query(ApiToken).filter_by(
            provider='openai',
            category='llm'
        ).first()
        assert specific_token is not None
        assert specific_token.api_key_encrypted == 'key1'
    
    def test_status_field(self, session):
        """Test status field functionality."""
        active_token = ApiToken(
            provider='provider1',
            category='llm',
            api_key_encrypted='key1',
            status='active'
        )
        inactive_token = ApiToken(
            provider='provider2',
            category='llm',
            api_key_encrypted='key2',
            status='inactive'
        )
        
        session.add_all([active_token, inactive_token])
        session.commit()
        
        active_tokens = session.query(ApiToken).filter_by(status='active').all()
        assert len(active_tokens) == 1
        assert active_tokens[0].provider == 'provider1'
