// Neo4j 5 Community 约束与索引（V1.2 附录 A.1/A.2）。幂等，可重复执行：make init
// 1) 六类节点 node_key 唯一（node_key = batch_id + ":" + entity_id，不同批次不共用物理节点）
CREATE CONSTRAINT college_node_key IF NOT EXISTS FOR (n:College) REQUIRE n.node_key IS UNIQUE;
CREATE CONSTRAINT professional_node_key IF NOT EXISTS FOR (n:Professional) REQUIRE n.node_key IS UNIQUE;
CREATE CONSTRAINT programplan_node_key IF NOT EXISTS FOR (n:ProgramPlan) REQUIRE n.node_key IS UNIQUE;
CREATE CONSTRAINT coursecategory_node_key IF NOT EXISTS FOR (n:CourseCategory) REQUIRE n.node_key IS UNIQUE;
CREATE CONSTRAINT course_node_key IF NOT EXISTS FOR (n:Course) REQUIRE n.node_key IS UNIQUE;
CREATE CONSTRAINT ruleclause_node_key IF NOT EXISTS FOR (n:RuleClause) REQUIRE n.node_key IS UNIQUE;

// 2) 按批次 + 业务 ID 查询
CREATE INDEX college_batch_entity IF NOT EXISTS FOR (n:College) ON (n.batch_id, n.entity_id);
CREATE INDEX professional_batch_entity IF NOT EXISTS FOR (n:Professional) ON (n.batch_id, n.entity_id);
CREATE INDEX programplan_batch_entity IF NOT EXISTS FOR (n:ProgramPlan) ON (n.batch_id, n.entity_id);
CREATE INDEX coursecategory_batch_entity IF NOT EXISTS FOR (n:CourseCategory) ON (n.batch_id, n.entity_id);
CREATE INDEX course_batch_entity IF NOT EXISTS FOR (n:Course) ON (n.batch_id, n.entity_id);
CREATE INDEX ruleclause_batch_entity IF NOT EXISTS FOR (n:RuleClause) ON (n.batch_id, n.entity_id);

// 3) 关系 relation_id 索引（Community 不提供关系唯一约束，唯一性由导入层用 MERGE + 检查保证）
CREATE INDEX belongs_to_relation_id IF NOT EXISTS FOR ()-[r:BELONGS_TO]-() ON (r.relation_id);
CREATE INDEX contains_relation_id IF NOT EXISTS FOR ()-[r:CONTAINS]-() ON (r.relation_id);
CREATE INDEX applies_to_relation_id IF NOT EXISTS FOR ()-[r:APPLIES_TO]-() ON (r.relation_id);
CREATE INDEX cites_relation_id IF NOT EXISTS FOR ()-[r:CITES]-() ON (r.relation_id);
CREATE INDEX prerequisite_of_relation_id IF NOT EXISTS FOR ()-[r:PREREQUISITE_OF]-() ON (r.relation_id);
