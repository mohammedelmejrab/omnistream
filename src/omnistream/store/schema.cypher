CREATE CONSTRAINT seen_item_hash IF NOT EXISTS FOR (n:SeenItem) REQUIRE n.hash IS UNIQUE;
CREATE CONSTRAINT bubble_id IF NOT EXISTS FOR (n:Bubble) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT fact_id IF NOT EXISTS FOR ()-[f:FACT]-() REQUIRE f.id IS UNIQUE;
CREATE INDEX fact_bubble_relation IF NOT EXISTS FOR ()-[f:FACT]-() ON (f.bubble_id, f.relation);
CREATE VECTOR INDEX entity_embedding IF NOT EXISTS FOR (e:Entity) ON e.embedding OPTIONS {indexConfig: {`vector.dimensions`: __DIM__, `vector.similarity_function`: 'cosine'}};
