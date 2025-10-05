from fs42.block_plan import BlockPlanEntry
from fs42.media_processor import MediaProcessor

class ReelCutter:
    @staticmethod
    def cut_reels_into_base(base_clip, reel_blocks, base_offset, base_duration, break_strategy, start_bump, end_bump, break_points=None):
        entries = []
        break_count = 0
        
        if break_points:
            break_points = MediaProcessor.calc_black_segments(break_points, base_clip.duration)
            #[print(x) for x in break_points]

        if start_bump:
            entries.append(BlockPlanEntry(start_bump["path"], 0, start_bump["duration"]))

        if reel_blocks:
            break_count = len(reel_blocks)

        if break_count <= 1 or break_strategy == "end" or break_strategy == "center":
            if break_strategy == "center":
                h_dur = base_duration/2
                h1 = BlockPlanEntry(base_clip.path, base_offset, h_dur)
                h2 = BlockPlanEntry(base_clip.path, base_offset+h_dur, h_dur)
                entries.append(h1)
            else:
                # then don't cut the base at all
                entries.append(BlockPlanEntry(base_clip.path, base_offset, base_duration))
            for _block in reel_blocks:
                # and put the reel at the end if there is one
                entries += _block.make_plan()
            if break_strategy == "center":
                entries.append(h2)
        else:
            # we know break count is greater than 1
            segment_duration = base_clip.duration / break_count
            offset = base_offset

            if not break_points:
                for i in range(break_count):
                    entries.append(BlockPlanEntry(base_clip.path, offset, segment_duration))
                    entries += reel_blocks[i].make_plan()
                    offset += segment_duration
            else:

                keep_going = True

                if len(break_points):
                    # Play first segment from start to first break point
                    # Use absolute chapter_start position, not cumulative offset
                    first_segment = break_points.pop(0)
                    segment_duration = first_segment["chapter_end"] - first_segment["chapter_start"]
                    entries.append(BlockPlanEntry(base_clip.path, first_segment["chapter_start"], segment_duration))

                while keep_going:

                    if len(reel_blocks):
                        reel_block = reel_blocks.pop(0)
                        entries += reel_block.make_plan()

                    if len(break_points):
                        this_bp = break_points.pop(0)
                        # Play content segment using absolute chapter_start position
                        segment_duration = this_bp["chapter_end"] - this_bp["chapter_start"]
                        e = BlockPlanEntry(base_clip.path, this_bp["chapter_start"], segment_duration)
                        entries.append(e)
                    
                        
                    if not len(break_points) and not len(reel_blocks):
                        keep_going = False

        if end_bump:
            entries.append(BlockPlanEntry(end_bump["path"], 0, end_bump["duration"]))

        return entries


    @staticmethod
    def cut_reels_into_clips(clips, reel_blocks, break_stategy, start_bump, end_bump):
        entries = []

        if start_bump:
            entries.append(BlockPlanEntry(start_bump.path, 0, start_bump.duration))

        if reel_blocks:
            break_count = len(reel_blocks)
        else:
            break_count = 0
        if break_count <= 1 or break_stategy == "end":
            # then don't cut the base at all
            for clip in clips:
                entries.append(BlockPlanEntry(clip.path, 0, clip.duration))
            for _block in reel_blocks:
                # and put the reel at the end if there is one
                entries += _block.make_plan()
        elif break_stategy == "center":
            # half clips, then all reels, then second half clips
            half_point = len(clips) // 2
            
            # First half of clips
            for i in range(half_point):
                clip = clips[i]
                entries.append(BlockPlanEntry(clip.path, 0, clip.duration))
            
            # All reels
            for _block in reel_blocks:
                entries += _block.make_plan()
            
            # Second half of clips
            for i in range(half_point, len(clips)):
                clip = clips[i]
                entries.append(BlockPlanEntry(clip.path, 0, clip.duration))
        else:
            clips_per_segment = 1
            if len(clips) > break_count:
                clips_per_segment = round(len(clips) / break_count)

            for i in range(len(clips)):
                clip = clips[i]
                entries.append(BlockPlanEntry(clip.path, 0, clip.duration))
                if len(reel_blocks) and (i % clips_per_segment) == 0:
                    reel_b = reel_blocks.pop(0)
                    entries += reel_b.make_plan()

            while len(reel_blocks):
                reel_b = reel_blocks.pop(0)
                entries += reel_b.make_plan()

        if end_bump:
            entries.append(BlockPlanEntry(end_bump.path, 0, end_bump.duration))

        return entries
