class CreatePipelineRuns < ActiveRecord::Migration[8.1]
  def change
    create_table :pipeline_runs do |t|
      t.references :video_project, null: false, foreign_key: true
      t.string :run_id, null: false
      t.string :status, default: "pending", null: false
      t.string :raw_video_path
      t.string :final_video_path
      t.string :subtitles_path
      t.integer :quality_score
      t.text :error_message
      t.jsonb :metadata, default: {}

      t.timestamps
    end
    add_index :pipeline_runs, :run_id, unique: true
    add_index :pipeline_runs, :status
  end
end
